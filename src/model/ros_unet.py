"""
Physics-Informed Rate of Spread (ROS) Generator
===============================================
A lightweight U-Net architecture that ingests spatial terrain, fuel, and weather 
data to output a 2D velocity field (Rate of Spread).

This field acts as the spatially-varying parameter R_f for the Level-Set PDE.

Channels Input (N, C, H, W):
0: Fire Mask (1 = burning, 0 = unburned)
1: Slope (Degrees)
2: Aspect Sin (Orientation)
3: Aspect Cos (Orientation)
4: Fuel Dryness Anomaly (NDVI z-score)
5: Wind U (m/s)
6: Wind V (m/s)

Output (N, 1, H, W):
ROS Field (m/min)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F

class DoubleConv(nn.Module):
    """(convolution => [BN] => ReLU) * 2"""
    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.double_conv = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True)
        )

    def forward(self, x):
        return self.double_conv(x)

class Down(nn.Module):
    """Downscaling with maxpool then double conv"""
    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.maxpool_conv = nn.Sequential(
            nn.MaxPool2d(2),
            DoubleConv(in_channels, out_channels)
        )

    def forward(self, x):
        return self.maxpool_conv(x)

class Up(nn.Module):
    """Upscaling then double conv"""
    def __init__(self, in_channels, out_channels, bilinear=True):
        super().__init__()

        # if bilinear, use the normal convolutions to reduce the number of channels
        if bilinear:
            self.up = nn.Upsample(scale_factor=2, mode='bilinear', align_corners=True)
            self.conv = DoubleConv(in_channels, out_channels)
        else:
            self.up = nn.ConvTranspose2d(in_channels, in_channels // 2, kernel_size=2, stride=2)
            self.conv = DoubleConv(in_channels, out_channels)

    def forward(self, x1, x2):
        x1 = self.up(x1)
        # input is CHW
        diffY = x2.size()[2] - x1.size()[2]
        diffX = x2.size()[3] - x1.size()[3]

        x1 = F.pad(x1, [diffX // 2, diffX - diffX // 2,
                        diffY // 2, diffY - diffY // 2])
        x = torch.cat([x2, x1], dim=1)
        return self.conv(x)

class ROSGeneratorUNet(nn.Module):
    def __init__(self, n_channels=7, bilinear=False):
        super(ROSGeneratorUNet, self).__init__()
        self.n_channels = n_channels
        self.bilinear = bilinear

        # Very lightweight backbone since we are modeling physics constraints, 
        # not complex visual textures.
        factor = 2 if bilinear else 1
        self.inc = DoubleConv(n_channels, 32)
        self.down1 = Down(32, 64)
        self.down2 = Down(64, 128)
        self.down3 = Down(128, 256 // factor)
        self.up1 = Up(256, 128 // factor, bilinear)
        self.up2 = Up(128, 64 // factor, bilinear)
        self.up3 = Up(64, 32, bilinear)
        
        # Output is a single channel: Rate of Spread (ROS)
        self.outc = nn.Conv2d(32, 1, kernel_size=1)
        
        # Softplus ensures ROS is always positive (fire cannot burn backwards)
        self.activation = nn.Softplus()

    def forward(self, x):
        x1 = self.inc(x)
        x2 = self.down1(x1)
        x3 = self.down2(x2)
        x4 = self.down3(x3)
        
        x = self.up1(x4, x3)
        x = self.up2(x, x2)
        x = self.up3(x, x1)
        logits = self.outc(x)
        
        return self.activation(logits)

if __name__ == "__main__":
    # Test the model with dummy data
    batch_size = 1
    channels = 7
    h, w = 128, 128
    
    dummy_input = torch.randn(batch_size, channels, h, w)
    model = ROSGeneratorUNet(n_channels=channels)
    
    out_ros = model(dummy_input)
    print(f"Input Shape: {dummy_input.shape}")
    print(f"ROS Field Shape: {out_ros.shape}")
    print(f"Min ROS: {out_ros.min().item():.3f}, Max ROS: {out_ros.max().item():.3f}")
