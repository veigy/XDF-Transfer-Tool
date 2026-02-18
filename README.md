# XDF Transfer Tool

Powerful mapping transfer utility for Bosch ME7 engine control units. This tool allows you to accurately transfer map definitions (XDF) from one binary file to another, even if the target file has offset changes or slight data modifications.

## Key Features

- **Deep Match (Context-Aware Scanning)**: Beyond simple byte-matching, the tool analyzes the surrounding data (context) to confirm the correct map location among multiple identical patterns.
- **Sequential Duplicate Resolution**: Automatically handles multiple identical maps (like those for different cylinders) by maintaining their relative sequence from the original file.
- **Fuzzy Search (Experimental)**: Intelligent recovery of missing maps using a configurable tolerance (+/- 10 raw values) and partial match threshold (80%). Ideal for finding maps in tuned or slightly different software versions.
- **Axis Synchronization**: Automatically identifies and transfers X and Y axes using deep context and offset guessing.
- **Smart UI**: Synchronized scrolling for side-by-side data comparison, color-coded results, and manual address resolution for ambiguous matches.

## How to Use

1. **Load XDF**: Select your original XDF definition file.
2. **Load SOURCE BIN**: Select the binary file that matches the original XDF.
3. **Load TARGET BIN**: Select the new binary file you want to transfer definitions into.
4. **Scan**: The tool automatically starts a deep scan.
5. **Fuzzy Search (Optional)**: If any maps are missing, use the "Fuzzy Search" button to locate them with higher tolerance.
6. **Export**: Save your new XDF file.

## Requirements

- Python 3.x
- PyQt6

## Development
```bash
# Install dependencies
pip install PyQt6

# Run the application
python main.py
```

---
*Developed for the VAG tuning community.*
