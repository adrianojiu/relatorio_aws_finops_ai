#!/usr/bin/env python3
"""
Launcher script for AWS Cost Report
"""

import sys
import os

# Add src to path
src_path = os.path.join(os.path.dirname(__file__), 'src')
sys.path.insert(0, src_path)

if __name__ == "__main__":
    # Import after path setup
    import config
    import utils
    from collectors import cost_explorer, csv_input
    from analyzers import cost_analysis
    from renderers import txt_report, excel_report
    from integrations import bedrock
    from main import main
    
    main()