import torch
import torch.nn as nn
import torchvision.transforms as transforms
import numpy as np
import matplotlib.pyplot as plt
from PIL import Image
import cv2
import os
import glob

# Set device
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"Using device: {device}")

# Define the UNet model architecture (must match your trained model)
class DoubleConv(nn.Module):
    """Double Convolution Block with optional Dropout for regularization"""
    def __init__(self, in_channels, out_channels, dropout_rate=0.1):
        super(DoubleConv, self).__init__()
        layers = [
            nn.Conv2d(in_channels, out_channels, 3, 1, 1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        ]

        if dropout_rate > 0:
            layers.append(nn.Dropout2d(dropout_rate))

        layers.extend([
            nn.Conv2d(out_channels, out_channels, 3, 1, 1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True)
        ])

        self.conv = nn.Sequential(*layers)

    def forward(self, x):
        return self.conv(x)

class UNet(nn.Module):
    def __init__(self, in_channels=3, out_channels=1, features=[64, 128, 256, 512], dropout_rate=0.1):
        super(UNet, self).__init__()
        self.ups = nn.ModuleList()
        self.downs = nn.ModuleList()
        self.pool = nn.MaxPool2d(kernel_size=2, stride=2)

        # Down part of UNET
        for feature in features:
            self.downs.append(DoubleConv(in_channels, feature, dropout_rate))
            in_channels = feature

        # Up part of UNET
        for feature in reversed(features):
            self.ups.append(
                nn.ConvTranspose2d(feature*2, feature, kernel_size=2, stride=2)
            )
            self.ups.append(DoubleConv(feature*2, feature, dropout_rate))

        self.bottleneck = DoubleConv(features[-1], features[-1]*2, dropout_rate)
        self.final_conv = nn.Conv2d(features[0], out_channels, kernel_size=1)

    def forward(self, x):
        skip_connections = []

        for down in self.downs:
            x = down(x)
            skip_connections.append(x)
            x = self.pool(x)

        x = self.bottleneck(x)
        skip_connections = skip_connections[::-1]

        for idx in range(0, len(self.ups), 2):
            x = self.ups[idx](x)
            skip_connection = skip_connections[idx//2]

            if x.shape != skip_connection.shape:
                x = torch.nn.functional.interpolate(x, size=skip_connection.shape[2:], mode='bilinear', align_corners=False)

            concat_skip = torch.cat((skip_connection, x), dim=1)
            x = self.ups[idx+1](concat_skip)

        return torch.sigmoid(self.final_conv(x))

def preprocess_sar_image(image_path, target_size=(256, 256)):
    """
    Preprocess SAR image for inference
    """
    # Load image (single channel SAR)
    image = Image.open(image_path).convert('L')
    original_size = image.size  # (width, height)
    
    # Resize
    image_resized = image.resize(target_size, Image.BILINEAR)
    
    # Convert to numpy
    image_np = np.array(image_resized).astype(np.float32)
    
    # Apply SAR log transform (same as in training)
    image_np = 10 * np.log10(image_np + 1e-8)
    min_val = np.percentile(image_np, 1)
    max_val = np.percentile(image_np, 99)
    image_np = np.clip((image_np - min_val) / (max_val - min_val + 1e-8), 0, 1)
    
    # Make pseudo-RGB by stacking grayscale 3 times
    image_rgb = np.stack([image_np, image_np, image_np], axis=-1)
    
    # Convert to tensor and add batch dimension
    image_tensor = torch.from_numpy(image_rgb.transpose(2, 0, 1)).float()
    image_tensor = image_tensor.unsqueeze(0)  # Add batch dimension
    
    return image_tensor, image_np, original_size

def postprocess_prediction(prediction, threshold=0.5, original_size=None):
    """
    Postprocess model prediction to get binary mask
    """
    # Convert to numpy and remove batch and channel dimensions
    pred_np = prediction.squeeze().cpu().numpy()
    
    # Apply threshold
    binary_mask = (pred_np > threshold).astype(np.uint8) * 255
    
    # Resize back to original size if needed
    if original_size:
        # original_size is (width, height) from PIL, need (height, width) for cv2
        original_size_cv = (original_size[1], original_size[0])
        binary_mask = cv2.resize(binary_mask, original_size_cv, interpolation=cv2.INTER_NEAREST)
        prob_mask = cv2.resize(pred_np, original_size_cv, interpolation=cv2.INTER_LINEAR)
    else:
        prob_mask = pred_np
    
    return binary_mask, prob_mask

def visualize_results(original_image_path, prob_mask, binary_mask, threshold=0.5, save_path=None):
    """
    Visualize original image, probability map, and binary prediction
    """
    # Load original image
    original_image = Image.open(original_image_path).convert('L')
    original_np = np.array(original_image)
    
    # Ensure all images have the same dimensions
    # Get the shape of the binary mask (which should be original size)
    h, w = binary_mask.shape
    
    # Resize original image to match binary mask if needed
    if original_np.shape != binary_mask.shape:
        original_np = cv2.resize(original_np, (w, h), interpolation=cv2.INTER_LINEAR)
    
    fig, axes = plt.subplots(2, 3, figsize=(15, 10))
    
    # Original SAR image
    axes[0, 0].imshow(original_np, cmap='gray')
    axes[0, 0].set_title('Original SAR Image')
    axes[0, 0].axis('off')
    
    # Probability map (resized to match)
    prob_resized = cv2.resize(prob_mask, (w, h)) if prob_mask.shape != binary_mask.shape else prob_mask
    im1 = axes[0, 1].imshow(prob_resized, cmap='jet', vmin=0, vmax=1)
    axes[0, 1].set_title('Flood Probability Map')
    axes[0, 1].axis('off')
    plt.colorbar(im1, ax=axes[0, 1], fraction=0.046, pad=0.04)
    
    # Binary prediction
    axes[0, 2].imshow(binary_mask, cmap='gray')
    axes[0, 2].set_title(f'Binary Prediction (threshold={threshold})')
    axes[0, 2].axis('off')
    
    # Overlay (original + prediction)
    overlay = original_np / 255.0
    overlay = np.stack([overlay, overlay, overlay], axis=-1)
    
    # Create red overlay for flood areas
    red_overlay = np.zeros_like(overlay)
    red_overlay[:, :, 0] = 1  # Red channel
    
    # Apply overlay where flood is predicted
    mask_normalized = binary_mask / 255.0
    overlay_with_flood = overlay.copy()
    for c in range(3):
        overlay_with_flood[:, :, c] = np.where(mask_normalized > 0, 
                                               overlay[:, :, c] * 0.5 + red_overlay[:, :, c] * 0.5,
                                               overlay[:, :, c])
    
    axes[1, 0].imshow(overlay_with_flood)
    axes[1, 0].set_title('Overlay (Flood in Red)')
    axes[1, 0].axis('off')
    
    # Histogram of probability distribution
    axes[1, 1].hist(prob_resized.flatten(), bins=50, alpha=0.7, color='blue')
    axes[1, 1].axvline(x=threshold, color='red', linestyle='--', label=f'Threshold={threshold}')
    axes[1, 1].set_xlabel('Flood Probability')
    axes[1, 1].set_ylabel('Frequency')
    axes[1, 1].set_title('Probability Distribution')
    axes[1, 1].legend()
    axes[1, 1].grid(True, alpha=0.3)
    
    # Flood percentage
    flood_percentage = (binary_mask > 0).sum() / binary_mask.size * 100
    axes[1, 2].text(0.5, 0.5, f'Flood Area: {flood_percentage:.2f}%', 
                   ha='center', va='center', fontsize=16, transform=axes[1, 2].transAxes)
    axes[1, 2].set_title('Flood Statistics')
    axes[1, 2].axis('off')
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"Visualization saved to: {save_path}")
    
    plt.show()

def calculate_flood_statistics(binary_mask, pixel_resolution_m=None):
    """
    Calculate flood statistics from the prediction
    
    Args:
        binary_mask: Binary mask (0 or 255)
        pixel_resolution_m: Pixel resolution in meters (if known)
    """
    total_pixels = binary_mask.size
    flood_pixels = np.sum(binary_mask > 0)
    flood_percentage = (flood_pixels / total_pixels) * 100
    
    stats = {
        'total_pixels': total_pixels,
        'flood_pixels': flood_pixels,
        'non_flood_pixels': total_pixels - flood_pixels,
        'flood_percentage': flood_percentage,
        'non_flood_percentage': 100 - flood_percentage
    }
    
    # Calculate area if resolution is provided
    if pixel_resolution_m:
        pixel_area_m2 = pixel_resolution_m ** 2
        flood_area_m2 = flood_pixels * pixel_area_m2
        stats['flood_area_m2'] = flood_area_m2
        stats['flood_area_ha'] = flood_area_m2 / 10000  # Hectares
        stats['flood_area_km2'] = flood_area_m2 / 1_000_000  # Square kilometers
    
    return stats

def main_inference():
    """
    Main inference function
    """
    # Defaults align with repo models/ (override with SAR_FLOOD_MODEL / SAR_FLOOD_IMAGE / SAR_FLOOD_OUT)
    _root = os.path.dirname(os.path.abspath(__file__))
    _repo = os.path.normpath(os.path.join(_root, ".."))
    _default_model = os.path.join(_repo, "models", "artifacts", "sar_flood", "sar_flood_unet.pth")
    _legacy_model = os.path.normpath(os.path.join(_repo, "backend", "models", "sar_flood_unet.pth"))
    _default_image = os.path.join(_repo, "models", "samples", "sar_flood", "p_withfloods.tif")
    _legacy_image = os.path.join(_root, "datasets", "p_withfloods.tif")

    MODEL_PATH = os.environ.get("SAR_FLOOD_MODEL")
    if not MODEL_PATH:
        MODEL_PATH = _default_model if os.path.isfile(_default_model) else _legacy_model

    IMAGE_PATH = os.environ.get("SAR_FLOOD_IMAGE")
    if not IMAGE_PATH:
        IMAGE_PATH = _default_image if os.path.isfile(_default_image) else _legacy_image
    SAVE_DIR = os.environ.get("SAR_FLOOD_OUT", os.path.join(_root, "inference_results"))
    
    # Create save directory
    if not os.path.exists(SAVE_DIR):
        os.makedirs(SAVE_DIR)
    
    # Inference parameters
    THRESHOLD = 0.5  # You can adjust this based on your optimal threshold
    IMAGE_SIZE = (256, 256)
    
    print("="*60)
    print("SAR FLOOD DETECTION INFERENCE")
    print("="*60)
    print(f"Model path: {MODEL_PATH}")
    print(f"Image path: {IMAGE_PATH}")
    print(f"Save directory: {SAVE_DIR}")
    print(f"Prediction threshold: {THRESHOLD}")
    print("="*60)
    
    # Check if files exist
    if not os.path.exists(MODEL_PATH):
        print(f"\n❌ Error: Model file not found at {MODEL_PATH}")
        print("Please check the model path")
        return
    
    if not os.path.exists(IMAGE_PATH):
        print(f"\n❌ Error: Image file not found at {IMAGE_PATH}")
        print("Please check the image path")
        return
    
    # Load model
    print("\n1. Loading model...")
    model = UNet(in_channels=3, out_channels=1, dropout_rate=0.0).to(device)
    
    try:
        # Try loading with weights_only=False to avoid compatibility issues
        checkpoint = torch.load(MODEL_PATH, map_location=device)
        model.load_state_dict(checkpoint)
        model.eval()
        print("   ✓ Model loaded successfully")
    except Exception as e:
        print(f"   ✗ Error loading model: {e}")
        return
    
    # Load and preprocess image
    print("\n2. Preprocessing image...")
    try:
        image_tensor, original_np, original_size = preprocess_sar_image(IMAGE_PATH, IMAGE_SIZE)
        image_tensor = image_tensor.to(device)
        print(f"   ✓ Image loaded and preprocessed")
        print(f"   Original size: {original_size}")
        print(f"   Input tensor shape: {image_tensor.shape}")
    except Exception as e:
        print(f"   ✗ Error preprocessing image: {e}")
        return
    
    # Run inference
    print("\n3. Running inference...")
    with torch.no_grad():
        prediction = model(image_tensor)
        print(f"   ✓ Inference complete")
        print(f"   Prediction shape: {prediction.shape}")
    
    # Postprocess prediction
    print("\n4. Postprocessing prediction...")
    binary_mask, prob_mask = postprocess_prediction(prediction, THRESHOLD, original_size)
    print(f"   ✓ Postprocessing complete")
    print(f"   Binary mask shape: {binary_mask.shape}")
    print(f"   Probability map shape: {prob_mask.shape}")
    
    # Calculate statistics
    print("\n5. Calculating flood statistics...")
    stats = calculate_flood_statistics(binary_mask)
    print("\n   📊 FLOOD STATISTICS:")
    print(f"   - Total pixels: {stats['total_pixels']:,}")
    print(f"   - Flood pixels: {stats['flood_pixels']:,}")
    print(f"   - Non-flood pixels: {stats['non_flood_pixels']:,}")
    print(f"   - Flood percentage: {stats['flood_percentage']:.2f}%")
    print(f"   - Non-flood percentage: {stats['non_flood_percentage']:.2f}%")
    
    # Save results
    print("\n6. Saving results...")
    
    # Save binary mask
    binary_mask_path = os.path.join(SAVE_DIR, "flood_prediction_mask.png")
    Image.fromarray(binary_mask).save(binary_mask_path)
    print(f"   ✓ Binary mask saved to: {binary_mask_path}")
    
    # Save probability map
    prob_mask_normalized = (prob_mask * 255).astype(np.uint8)
    prob_mask_path = os.path.join(SAVE_DIR, "flood_probability_map.png")
    Image.fromarray(prob_mask_normalized).save(prob_mask_path)
    print(f"   ✓ Probability map saved to: {prob_mask_path}")
    
    # Save statistics to text file
    stats_path = os.path.join(SAVE_DIR, "flood_statistics.txt")
    with open(stats_path, 'w') as f:
        f.write("SAR FLOOD DETECTION RESULTS\n")
        f.write("="*50 + "\n\n")
        f.write(f"Image: {IMAGE_PATH}\n")
        f.write(f"Model: {MODEL_PATH}\n")
        f.write(f"Threshold: {THRESHOLD}\n\n")
        f.write("STATISTICS:\n")
        f.write(f"Total pixels: {stats['total_pixels']:,}\n")
        f.write(f"Flood pixels: {stats['flood_pixels']:,}\n")
        f.write(f"Non-flood pixels: {stats['non_flood_pixels']:,}\n")
        f.write(f"Flood percentage: {stats['flood_percentage']:.2f}%\n")
        f.write(f"Non-flood percentage: {stats['non_flood_percentage']:.2f}%\n")
    print(f"   ✓ Statistics saved to: {stats_path}")
    
    # Visualize results
    print("\n7. Generating visualization...")
    vis_path = os.path.join(SAVE_DIR, "inference_visualization.png")
    visualize_results(IMAGE_PATH, prob_mask, binary_mask, THRESHOLD, vis_path)
    
    print("\n" + "="*60)
    print("✅ INFERENCE COMPLETE!")
    print(f"All results saved to: {SAVE_DIR}")
    print("="*60)
    
    return {
        'binary_mask': binary_mask,
        'probability_map': prob_mask,
        'statistics': stats
    }

def test_different_thresholds(model, image_tensor, original_size, thresholds=[0.3, 0.4, 0.5, 0.6, 0.7]):
    """
    Test different thresholds and show results
    """
    print("\n" + "="*60)
    print("TESTING DIFFERENT THRESHOLDS")
    print("="*60)
    
    with torch.no_grad():
        prediction = model(image_tensor)
    
    results = []
    for threshold in thresholds:
        binary_mask, prob_mask = postprocess_prediction(prediction, threshold, original_size)
        flood_percentage = (binary_mask > 0).sum() / binary_mask.size * 100
        results.append({
            'threshold': threshold,
            'flood_percentage': flood_percentage
        })
        print(f"Threshold {threshold}: Flood area = {flood_percentage:.2f}%")
    
    # Plot threshold comparison
    fig, ax = plt.subplots(figsize=(10, 6))
    thresholds_vals = [r['threshold'] for r in results]
    flood_pcts = [r['flood_percentage'] for r in results]
    
    ax.plot(thresholds_vals, flood_pcts, marker='o', linewidth=2, markersize=8)
    ax.set_xlabel('Threshold', fontsize=12)
    ax.set_ylabel('Flood Area (%)', fontsize=12)
    ax.set_title('Effect of Threshold on Flood Detection', fontsize=14)
    ax.grid(True, alpha=0.3)
    
    # Add value labels
    for i, (t, p) in enumerate(zip(thresholds_vals, flood_pcts)):
        ax.annotate(f'{p:.1f}%', (t, p), xytext=(5, 5), textcoords='offset points')
    
    plt.tight_layout()
    plt.savefig('/content/inference_results/threshold_analysis.png', dpi=300, bbox_inches='tight')
    plt.show()
    
    return results

if __name__ == "__main__":
    # Run single image inference
    results = main_inference()
    
    # Optional: If you want to test different thresholds after inference
    if results:
        print("\n💡 Tip: You can adjust the threshold to change flood sensitivity")
        print("   - Lower threshold: More sensitive (detects more potential floods)")
        print("   - Higher threshold: More specific (reduces false positives)")