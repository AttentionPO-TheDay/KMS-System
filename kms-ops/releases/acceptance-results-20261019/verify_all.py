import json
from pathlib import Path
from verify import main

main(json.loads((Path(__file__).parent / 'manifest.json').read_text())['cases'])
