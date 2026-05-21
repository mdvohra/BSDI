import os
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import cv2
from PIL import Image
import matplotlib.pyplot as plt
import albumentations as A
from albumentations.pytorch import ToTensorV2

# ==================== RESUNET-A ARCHITECTURE ====================
class ResidualConvBlock(nn.Module):
    """Residual Convolutional Block with BatchNorm and ReLU"""
    def __init__(self, in_channels, out_channels, stride=1):
        super(ResidualConvBlock, self).__init__()
        
        self.conv1 = nn.Conv2d(in_channels, out_channels, kernel_size=3, 
                              stride=stride, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(out_channels)
        self.relu = nn.ReLU(inplace=True)
        self.conv2 = nn.Conv2d(out_channels, out_channels, kernel_size=3, 
                              padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(out_channels)
        
        # Skip connection
        self.skip_connection = nn.Sequential()
        if stride != 1 or in_channels != out_channels:
            self.skip_connection = nn.Sequential(
                nn.Conv2d(in_channels, out_channels, kernel_size=1, 
                         stride=stride, bias=False),
                nn.BatchNorm2d(out_channels)
            )
    
    def forward(self, x):
        identity = self.skip_connection(x)
        
        out = self.conv1(x)
        out = self.bn1(out)
        out = self.relu(out)
        
        out = self.conv2(out)
        out = self.bn2(out)
        
        out += identity
        out = self.relu(out)
        
        return out

class ASPPModule(nn.Module):
    """Atrous Spatial Pyramid Pooling for multi-scale feature extraction"""
    def __init__(self, in_channels, out_channels=256):
        super(ASPPModule, self).__init__()
        
        # 1x1 convolution
        self.conv1x1 = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True)
        )
        
        # 3x3 convolution with rate=6
        self.conv3x3_1 = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, 
                     padding=6, dilation=6, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True)
        )
        
        # 3x3 convolution with rate=12
        self.conv3x3_2 = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, 
                     padding=12, dilation=12, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True)
        )
        
        # 3x3 convolution with rate=18
        self.conv3x3_3 = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, 
                     padding=18, dilation=18, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True)
        )
        
        # Global average pooling
        self.global_avg_pool = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Conv2d(in_channels, out_channels, kernel_size=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True)
        )
        
        self.conv1x1_out = nn.Sequential(
            nn.Conv2d(out_channels * 5, out_channels, kernel_size=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True)
        )
        
    def forward(self, x):
        b, c, h, w = x.size()
        
        # Branch 1: 1x1 convolution
        branch1 = self.conv1x1(x)
        
        # Branch 2: 3x3 dilation=6
        branch2 = self.conv3x3_1(x)
        
        # Branch 3: 3x3 dilation=12
        branch3 = self.conv3x3_2(x)
        
        # Branch 4: 3x3 dilation=18
        branch4 = self.conv3x3_3(x)
        
        # Branch 5: Global average pooling
        branch5 = self.global_avg_pool(x)
        branch5 = F.interpolate(branch5, size=(h, w), mode='bilinear', align_corners=True)
        
        # Concatenate all branches
        out = torch.cat([branch1, branch2, branch3, branch4, branch5], dim=1)
        out = self.conv1x1_out(out)
        
        return out

class AttentionGate(nn.Module):
    """Attention Gate for better feature fusion"""
    def __init__(self, F_g, F_l, F_int):
        super(AttentionGate, self).__init__()
        
        self.W_g = nn.Sequential(
            nn.Conv2d(F_g, F_int, kernel_size=1, stride=1, padding=0, bias=True),
            nn.BatchNorm2d(F_int)
        )
        
        self.W_x = nn.Sequential(
            nn.Conv2d(F_l, F_int, kernel_size=1, stride=1, padding=0, bias=True),
            nn.BatchNorm2d(F_int)
        )
        
        self.psi = nn.Sequential(
            nn.Conv2d(F_int, 1, kernel_size=1, stride=1, padding=0, bias=True),
            nn.BatchNorm2d(1),
            nn.Sigmoid()
        )
        
        self.relu = nn.ReLU(inplace=True)
        
    def forward(self, g, x):
        g1 = self.W_g(g)
        x1 = self.W_x(x)
        if g1.shape[2:] != x1.shape[2:]:
            g1 = F.interpolate(g1, size=x1.shape[2:], mode='bilinear', align_corners=True)
        psi = self.relu(g1 + x1)
        psi = self.psi(psi)
        return x * psi

class ResUNetA(nn.Module):
    """ResUNet-a: Advanced UNet with Residual blocks, ASPP, and Attention"""
    def __init__(self, in_channels=3, out_channels=1, features=[64, 128, 256, 512, 1024]):
        super(ResUNetA, self).__init__()
        
        # Encoder path
        self.encoder1 = ResidualConvBlock(in_channels, features[0])
        self.pool1 = nn.MaxPool2d(kernel_size=2, stride=2)
        
        self.encoder2 = ResidualConvBlock(features[0], features[1])
        self.pool2 = nn.MaxPool2d(kernel_size=2, stride=2)
        
        self.encoder3 = ResidualConvBlock(features[1], features[2])
        self.pool3 = nn.MaxPool2d(kernel_size=2, stride=2)
        
        self.encoder4 = ResidualConvBlock(features[2], features[3])
        self.pool4 = nn.MaxPool2d(kernel_size=2, stride=2)
        
        # Bridge with ASPP
        self.bridge = ResidualConvBlock(features[3], features[4])
        self.aspp = ASPPModule(features[4], features[4] // 2)
        
        # Decoder path with attention gates
        self.attention4 = AttentionGate(F_g=features[4] // 2, F_l=features[3], F_int=features[3] // 2)
        self.up_conv4 = nn.ConvTranspose2d(features[4] // 2, features[3], kernel_size=2, stride=2)
        self.decoder4 = ResidualConvBlock(features[3] * 2, features[3])
        
        self.attention3 = AttentionGate(F_g=features[3], F_l=features[2], F_int=features[2] // 2)
        self.up_conv3 = nn.ConvTranspose2d(features[3], features[2], kernel_size=2, stride=2)
        self.decoder3 = ResidualConvBlock(features[2] * 2, features[2])
        
        self.attention2 = AttentionGate(F_g=features[2], F_l=features[1], F_int=features[1] // 2)
        self.up_conv2 = nn.ConvTranspose2d(features[2], features[1], kernel_size=2, stride=2)
        self.decoder2 = ResidualConvBlock(features[1] * 2, features[1])
        
        self.attention1 = AttentionGate(F_g=features[1], F_l=features[0], F_int=features[0] // 2)
        self.up_conv1 = nn.ConvTranspose2d(features[1], features[0], kernel_size=2, stride=2)
        self.decoder1 = ResidualConvBlock(features[0] * 2, features[0])
        
        # Final output layer
        self.final_conv = nn.Sequential(
            nn.Conv2d(features[0], out_channels, kernel_size=1),
            nn.Sigmoid()
        )
        
        # Initialize weights
        self._initialize_weights()
    
    def _initialize_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)
    
    def forward(self, x):
        # Encoder
        e1 = self.encoder1(x)  # 64 channels
        e2 = self.encoder2(self.pool1(e1))  # 128 channels
        e3 = self.encoder3(self.pool2(e2))  # 256 channels
        e4 = self.encoder4(self.pool3(e3))  # 512 channels
        
        # Bridge with ASPP
        bridge = self.bridge(self.pool4(e4))  # 1024 channels
        bridge = self.aspp(bridge)  # 512 channels
        
        # Decoder with attention
        a4 = self.attention4(g=bridge, x=e4)
        d4 = self.up_conv4(bridge)
        d4 = torch.cat((a4, d4), dim=1)
        d4 = self.decoder4(d4)
        
        d3 = self.up_conv3(d4)
        a3 = self.attention3(g=d4, x=e3)
        d3 = torch.cat((a3, d3), dim=1)
        d3 = self.decoder3(d3)
        
        d2 = self.up_conv2(d3)
        a2 = self.attention2(g=d3, x=e2)
        d2 = torch.cat((a2, d2), dim=1)
        d2 = self.decoder2(d2)
        
        d1 = self.up_conv1(d2)
        a1 = self.attention1(g=d2, x=e1)
        d1 = torch.cat((a1, d1), dim=1)
        d1 = self.decoder1(d1)
        
        # Final output
        out = self.final_conv(d1)
        return out

# ==================== INFERENCE CONFIGURATION ====================
def setup_inference(model_path, device=None):
    """
    Setup model for inference
    
    Args:
        model_path: Path to the trained model weights
        device: Device to run inference on ('cuda' or 'cpu')
    
    Returns:
        model: Loaded model in eval mode
        device: Device being used
    """
    if device is None:
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    
    print(f"Using device: {device}")
    
    # Initialize model
    model = ResUNetA(in_channels=3, out_channels=1).to(device)
    
    # Load weights
    model.load_state_dict(torch.load(model_path, map_location=device))
    model.eval()
    
    print("✅ Model loaded successfully!")
    
    return model, device

def preprocess_image(image_path, img_size=256):
    """
    Preprocess image for inference
    
    Args:
        image_path: Path to input image
        img_size: Target size for the model
    
    Returns:
        original_image: Original image as numpy array (RGB)
        tensor: Preprocessed image tensor ready for model input
    """
    # Load image
    image = Image.open(image_path).convert('RGB')
    original_image = np.array(image)
    
    # Create transform
    transform = A.Compose([
        A.Resize(img_size, img_size),
        ToTensorV2()
    ])
    
    # Apply transform
    augmented = transform(image=original_image)
    tensor = augmented['image'].float().unsqueeze(0)
    
    return original_image, tensor

def predict_mask(model, image_tensor, device, threshold=0.5, sharpen=True):
    """
    Predict mask for input image
    
    Args:
        model: Loaded model
        image_tensor: Preprocessed image tensor
        device: Device to run inference on
        threshold: Threshold for binary mask (default: 0.5)
        sharpen: Whether to apply sharpening to the output (default: True)
    
    Returns:
        pred_prob: Probability mask
        pred_binary: Binary mask
        pred_sharp: Sharpened mask (if sharpen=True, else None)
    """
    # Sharpen kernel
    SHARPEN_KERNEL = np.array([
        [0, -1, 0],
        [-1, 10, -1],
        [0, -1, 0]
    ], dtype=np.float32)
    
    # Move tensor to device and predict
    image_tensor = image_tensor.to(device)
    
    with torch.no_grad():
        pred = model(image_tensor)
        pred_prob = pred[0, 0].cpu().numpy()
    
    # Convert to binary
    pred_binary = (pred_prob > threshold).astype(np.uint8)
    
    # Apply sharpening if requested
    if sharpen:
        pred_sharp = cv2.filter2D(pred_binary * 255, -1, SHARPEN_KERNEL)
    else:
        pred_sharp = None
    
    return pred_prob, pred_binary, pred_sharp

def visualize_inference(image_path, model, device, threshold=0.5, save_path=None):
    """
    Visualize inference results
    
    Args:
        image_path: Path to input image
        model: Loaded model
        device: Device for inference
        threshold: Threshold for binary mask
        save_path: Path to save the visualization (optional)
    """
    # Preprocess
    original_image, tensor = preprocess_image(image_path)
    
    # Predict
    pred_prob, pred_binary, pred_sharp = predict_mask(model, tensor, device, threshold)
    
    # Create visualization
    fig, axes = plt.subplots(1, 4, figsize=(16, 4))
    
    axes[0].imshow(original_image)
    axes[0].set_title('Original Image')
    axes[0].axis('off')
    
    axes[1].imshow(pred_prob, cmap='viridis')
    axes[1].set_title('Probability Mask')
    axes[1].axis('off')
    
    axes[2].imshow(pred_binary, cmap='gray')
    axes[2].set_title(f'Binary Mask (th={threshold})')
    axes[2].axis('off')
    
    axes[3].imshow(pred_sharp, cmap='gray')
    axes[3].set_title('Sharpened Mask')
    axes[3].axis('off')
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"✅ Visualization saved to {save_path}")
    
    plt.show()

def batch_inference(image_dir, model, device, output_dir=None, threshold=0.5):
    """
    Run inference on all images in a directory
    
    Args:
        image_dir: Directory containing images
        model: Loaded model
        device: Device for inference
        output_dir: Directory to save outputs (optional)
        threshold: Threshold for binary mask
    
    Returns:
        results: List of dictionaries containing predictions
    """
    # Get all image files
    image_extensions = ['.jpg', '.jpeg', '.png', '.tif', '.tiff']
    image_files = []
    
    for ext in image_extensions:
        image_files.extend(glob.glob(os.path.join(image_dir, f"*{ext}")))
        image_files.extend(glob.glob(os.path.join(image_dir, f"*{ext.upper()}")))
    
    image_files = list(set(image_files))  # Remove duplicates
    
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        masks_dir = os.path.join(output_dir, 'masks')
        visualizations_dir = os.path.join(output_dir, 'visualizations')
        os.makedirs(masks_dir, exist_ok=True)
        os.makedirs(visualizations_dir, exist_ok=True)
    
    results = []
    
    print(f"Processing {len(image_files)} images...")
    
    for img_path in tqdm(image_files):
        # Get filename
        fname = os.path.splitext(os.path.basename(img_path))[0]
        
        # Preprocess and predict
        original_image, tensor = preprocess_image(img_path)
        pred_prob, pred_binary, pred_sharp = predict_mask(model, tensor, device, threshold)
        
        result = {
            'image_path': img_path,
            'filename': fname,
            'original_image': original_image,
            'probability_mask': pred_prob,
            'binary_mask': pred_binary,
            'sharpened_mask': pred_sharp
        }
        
        # Save outputs if output_dir specified
        if output_dir:
            # Save binary mask
            cv2.imwrite(os.path.join(masks_dir, f"{fname}_binary.png"), pred_binary * 255)
            
            # Save sharpened mask
            cv2.imwrite(os.path.join(masks_dir, f"{fname}_sharp.png"), pred_sharp)
            
            # Save probability mask
            plt.imsave(os.path.join(masks_dir, f"{fname}_prob.png"), pred_prob, cmap='viridis')
            
            # Create and save visualization
            fig, axes = plt.subplots(1, 4, figsize=(16, 4))
            axes[0].imshow(original_image)
            axes[0].set_title('Original')
            axes[0].axis('off')
            axes[1].imshow(pred_prob, cmap='viridis')
            axes[1].set_title('Probability')
            axes[1].axis('off')
            axes[2].imshow(pred_binary, cmap='gray')
            axes[2].set_title('Binary')
            axes[2].axis('off')
            axes[3].imshow(pred_sharp, cmap='gray')
            axes[3].set_title('Sharpened')
            axes[3].axis('off')
            plt.tight_layout()
            plt.savefig(os.path.join(visualizations_dir, f"{fname}_visualization.png"), dpi=150, bbox_inches='tight')
            plt.close()
        
        results.append(result)
    
    print(f"✅ Processed {len(results)} images")
    
    if output_dir:
        print(f"📁 Outputs saved to: {output_dir}")
        print(f"   - Masks: {masks_dir}")
        print(f"   - Visualizations: {visualizations_dir}")
    
    return results

# ==================== MAIN EXECUTION ====================
if __name__ == "__main__":
    import glob
    from tqdm import tqdm
    
    # Configuration — repo-relative default (same layout as model_paths.artifact_dir)
    _ROOT = os.path.dirname(os.path.abspath(__file__))
    MODEL_PATH = os.path.join(
        _ROOT, "models", "artifacts", "solar_panel", "solarpanel_new.pth"
    )
    IMAGE_PATH = r"C:\Users\MohammadVohra\Desktop\new\Tile5_Clip6.tif"
    OUTPUT_DIR = "./inference_results"
    
    # Setup model
    model, device = setup_inference(MODEL_PATH)
    
    # Single image inference with visualization
    print("\n🎯 Running inference on single image...")
    visualize_inference(IMAGE_PATH, model, device, threshold=0.5, save_path="./single_image_result.png")
    
    # Optional: Batch inference on directory
    # IMAGE_DIR = "path/to/your/images/folder"
    # results = batch_inference(IMAGE_DIR, model, device, output_dir=OUTPUT_DIR, threshold=0.5)