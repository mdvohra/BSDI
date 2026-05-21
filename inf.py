import torch
import torch.nn as nn
import torch.nn.functional as TF
import numpy as np
import matplotlib.pyplot as plt
from PIL import Image
import cv2
import albumentations as A
from albumentations.pytorch import ToTensorV2
import os

# Set device
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"Using device: {device}")

# ─────────────────────────────────────────────
# MODEL DEFINITION (same as training)
# ─────────────────────────────────────────────
class DoubleConv(nn.Module):
    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, 3, 1, 1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, 3, 1, 1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.conv(x)


class UNet(nn.Module):
    def __init__(self, in_channels=3, out_channels=1, features=[64, 128, 256, 512]):
        super().__init__()
        self.ups   = nn.ModuleList()
        self.downs = nn.ModuleList()
        self.pool  = nn.MaxPool2d(2, 2)

        for feature in features:
            self.downs.append(DoubleConv(in_channels, feature))
            in_channels = feature

        for feature in reversed(features):
            self.ups.append(nn.ConvTranspose2d(feature * 2, feature, 2, 2))
            self.ups.append(DoubleConv(feature * 2, feature))

        self.bottleneck = DoubleConv(features[-1], features[-1] * 2)
        self.final_conv = nn.Conv2d(features[0], out_channels, 1)

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
            skip = skip_connections[idx // 2]
            if x.shape != skip.shape:
                x = TF.interpolate(x, size=skip.shape[2:])
            x = self.ups[idx + 1](torch.cat((skip, x), dim=1))

        return torch.sigmoid(self.final_conv(x))

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────
CONFIG = {
    "model_path": "/content/drive/MyDrive/Bahrain/finetuned_modelnew1.pth",  # Your fine-tuned model
    "img_size": 256,
    "threshold": 0.5,
}

# ─────────────────────────────────────────────
# INFERENCE FUNCTION
# ─────────────────────────────────────────────
def infer_single_image(model, img_path, threshold=0.5, save_mask_path=None, save_overlay_path=None):
    """
    Run inference on a single image
    
    Args:
        model: trained UNet model
        img_path: path to input image
        threshold: threshold for binary segmentation
        save_mask_path: path to save the binary mask
        save_overlay_path: path to save overlay visualization
    
    Returns:
        pred_mask: binary mask (uint8, 0 or 255)
        pred_prob: probability map (float, 0-1)
    """
    model.eval()
    
    # Load and preprocess image
    image = np.array(Image.open(img_path).convert("RGB"))
    orig_h, orig_w = image.shape[:2]
    
    # Transform for inference
    transform = A.Compose([
        A.Resize(CONFIG["img_size"], CONFIG["img_size"]),
        A.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
        ToTensorV2(),
    ])
    
    # Apply transform
    transformed = transform(image=image)
    tensor = transformed["image"].unsqueeze(0).float().to(device)
    
    # Inference
    with torch.no_grad():
        pred_prob = model(tensor).squeeze().cpu().numpy()
    
    # Resize back to original size
    pred_prob_resized = cv2.resize(pred_prob, (orig_w, orig_h), interpolation=cv2.INTER_LINEAR)
    
    # Apply threshold
    pred_mask = (pred_prob_resized > threshold).astype(np.uint8) * 255
    
    # Save mask if path provided
    if save_mask_path:
        Image.fromarray(pred_mask).save(save_mask_path)
        print(f"  ✓ Mask saved to {save_mask_path}")
    
    # Save overlay if path provided
    if save_overlay_path:
        create_overlay(image, pred_mask, save_overlay_path)
    
    return pred_mask, pred_prob_resized


def create_overlay(image, mask, save_path, alpha=0.5):
    """
    Create overlay of mask on original image
    
    Args:
        image: original RGB image (numpy array)
        mask: binary mask (0 or 255)
        save_path: path to save overlay
        alpha: transparency of mask overlay
    """
    # Create colored mask (red for buildings)
    colored_mask = np.zeros_like(image)
    colored_mask[:, :, 0] = mask  # Red channel
    
    # Overlay mask on image
    overlay = cv2.addWeighted(image, 1 - alpha, colored_mask, alpha, 0)
    
    # Save
    Image.fromarray(overlay).save(save_path)
    print(f"  ✓ Overlay saved to {save_path}")


def visualize_results(image_path, mask, prob, threshold=0.5):
    """
    Display inference results
    """
    # Load original image
    original = np.array(Image.open(image_path).convert("RGB"))
    
    # Create figure
    fig, axes = plt.subplots(1, 4, figsize=(20, 5))
    
    # Original image
    axes[0].imshow(original)
    axes[0].set_title("Original Image")
    axes[0].axis("off")
    
    # Probability map
    im1 = axes[1].imshow(prob, cmap="hot")
    axes[1].set_title("Probability Map")
    axes[1].axis("off")
    plt.colorbar(im1, ax=axes[1], fraction=0.046, pad=0.04)
    
    # Binary mask
    axes[2].imshow(mask, cmap="gray")
    axes[2].set_title(f"Binary Mask (threshold={threshold})")
    axes[2].axis("off")
    
    # Overlay
    colored_mask = np.zeros_like(original)
    colored_mask[:, :, 0] = mask
    overlay = cv2.addWeighted(original, 0.7, colored_mask, 0.3, 0)
    axes[3].imshow(overlay)
    axes[3].set_title("Overlay")
    axes[3].axis("off")
    
    plt.tight_layout()
    plt.savefig("/content/inference_visualization.png", dpi=150)
    plt.show()
    
    # Print statistics
    building_pixels = np.sum(mask > 0)
    total_pixels = mask.shape[0] * mask.shape[1]
    building_percentage = (building_pixels / total_pixels) * 100
    
    print("\n" + "="*50)
    print("INFERENCE RESULTS")
    print("="*50)
    print(f"  Image size: {mask.shape[1]} x {mask.shape[0]}")
    print(f"  Building pixels: {building_pixels:,} / {total_pixels:,}")
    print(f"  Building coverage: {building_percentage:.2f}%")
    print(f"  Mean probability: {prob.mean():.4f}")
    print(f"  Max probability: {prob.max():.4f}")
    print("="*50)


# ─────────────────────────────────────────────
# BATCH INFERENCE ON MULTIPLE IMAGES
# ─────────────────────────────────────────────
def batch_inference(model, image_folder, output_folder, threshold=0.5):
    """
    Run inference on all images in a folder
    
    Args:
        model: trained model
        image_folder: folder containing images
        output_folder: folder to save masks
        threshold: threshold for binary segmentation
    """
    os.makedirs(output_folder, exist_ok=True)
    os.makedirs(os.path.join(output_folder, "masks"), exist_ok=True)
    os.makedirs(os.path.join(output_folder, "overlays"), exist_ok=True)
    
    # Get all images
    image_extensions = ["*.tif", "*.tiff", "*.png", "*.jpg", "*.jpeg"]
    images = []
    for ext in image_extensions:
        images.extend(glob.glob(os.path.join(image_folder, ext)))
    images = sorted(images)
    
    print(f"\nFound {len(images)} images for batch inference")
    
    for i, img_path in enumerate(images):
        print(f"\n[{i+1}/{len(images)}] Processing: {os.path.basename(img_path)}")
        
        # Generate output paths
        base_name = os.path.splitext(os.path.basename(img_path))[0]
        mask_path = os.path.join(output_folder, "masks", f"{base_name}_mask.png")
        overlay_path = os.path.join(output_folder, "overlays", f"{base_name}_overlay.png")
        
        # Run inference
        mask, prob = infer_single_image(
            model, img_path, threshold, 
            save_mask_path=mask_path, 
            save_overlay_path=overlay_path
        )
        
        print(f"  ✓ Building coverage: {(mask > 0).sum() / mask.size * 100:.2f}%")


# ─────────────────────────────────────────────
# MAIN INFERENCE
# ─────────────────────────────────────────────
def main():
    print("\n" + "="*55)
    print("  BUILDING SEGMENTATION INFERENCE")
    print("="*55)
    
    # Load model
    print("\n[1/3] Loading fine-tuned model...")
    model = UNet(in_channels=3, out_channels=1).to(device)
    
    # Load the saved weights
    checkpoint = torch.load(CONFIG["model_path"], map_location=device)
    
    # Handle different checkpoint formats
    if isinstance(checkpoint, dict):
        if "model_state_dict" in checkpoint:
            state_dict = checkpoint["model_state_dict"]
        else:
            state_dict = checkpoint
    else:
        state_dict = checkpoint
    
    # Remove 'module.' prefix if present
    state_dict = {k.replace("module.", ""): v for k, v in state_dict.items()}
    
    # Load weights
    model.load_state_dict(state_dict)
    model = model.to(device)
    model.eval()
    print("  ✓ Model loaded successfully")
    
    # Inference on single image
    print("\n[2/3] Running inference on /content/chip_0.tif...")
    image_path = "/content/drive/MyDrive/Bahrain/output_chips_folderchips1/chip_100.tif"
    
    if not os.path.exists(image_path):
        print(f"  ✗ Image not found: {image_path}")
        print("  Please check the path or upload the image to /content/")
        return None, None
    
    # Run inference with saving options
    mask, prob = infer_single_image(
        model, 
        image_path, 
        threshold=CONFIG["threshold"],
        save_mask_path="/content/chip_0_predicted_mask.png",
        save_overlay_path="/content/chip_0_overlay.png"
    )
    
    # Visualize results
    print("\n[3/3] Visualizing results...")
    visualize_results(image_path, mask, prob, threshold=CONFIG["threshold"])
    
    print("\n✓ Inference complete!")
    print("  Saved files:")
    print("    - Mask: /content/chip_0_predicted_mask.png")
    print("    - Overlay: /content/chip_0_overlay.png")
    print("    - Visualization: /content/inference_visualization.png")
    
    return mask, prob


# Optional: Run batch inference on multiple chips
def batch_inference_example():
    """
    Example function for batch inference on multiple chip images
    """
    print("\n" + "="*55)
    print("  BATCH INFERENCE EXAMPLE")
    print("="*55)
    
    # Load model
    model = UNet(in_channels=3, out_channels=1).to(device)
    checkpoint = torch.load(CONFIG["model_path"], map_location=device)
    
    if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint:
        state_dict = checkpoint["model_state_dict"]
    else:
        state_dict = checkpoint
    
    state_dict = {k.replace("module.", ""): v for k, v in state_dict.items()}
    model.load_state_dict(state_dict)
    model = model.to(device)
    model.eval()
    
    # Run batch inference on folder containing chips
    input_folder = "/content/drive/MyDrive/Bahrain/output_chips_folderchips1"  # Change to your folder path
    output_folder = "/content/batch_results"
    
    if os.path.exists(input_folder):
        batch_inference(model, input_folder, output_folder, threshold=0.5)
    else:
        print(f"  ✗ Folder not found: {input_folder}")
        print("  Update the input_folder path in batch_inference_example()")


if __name__ == "__main__":
    # Run single image inference
    mask, probability = main()
    
    # Uncomment below to run batch inference on multiple images
    # batch_inference_example()