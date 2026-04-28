# Photo Editor - Crop, Rotate, Formatting

Feature Details
Open Folder     Loads all JPG, PNG, BMP, WEBP (+ HEIC with pillow-heif)
Crop Tool       Click-drag to create; drag corners/edges to resize; drag inside to move
Overlay         Semi-transparent dark mask outside crop + rule-of-thirds grid
Aspect Ratios   Free / 1:1 / 16:9 / 4:3 toggle buttons in the top bar
Navigation      ← → buttons + keyboard arrow keys; shows 1 / N counter
Zoom & Pan      Mouse wheel to zoom around cursor; middle-click drag to pan
Save            Overwrite original OR pick a new output folder
Save All        Batch-applies current crop region to every image in the folder
Lazy loading    Images load on-demand — handles 100+ image folders easily
Shortcuts       Ctrl+S save, Ctrl+O open, Escape/Ctrl+Z reset crop

## Setup

### Create virtual enviroment
python -m venv .venv

### Installation
pip install PyQt5 Pillow pillow-heif PyQt5-stubs


## Usage

### Activate virtual enviroment
.\.venv\Scripts\activate

### Run
python photo_editor.py



