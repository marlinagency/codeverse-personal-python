import os
import sys
import time
import logging

# Add backend/src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../Downloads/agent-of/backend/src")))

# Configure verbose logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout
)

from codeverse_api.config import get_settings
from codeverse_api.dependencies import build_llm_provider
from codeverse_core.theme_mapping.generator import TaxonomyThemeDictionaryGenerator

def main():
    settings = get_settings()
    print(f"Using provider: {settings.llm_provider}", flush=True)
    print(f"Using model: {settings.fireworks_model}", flush=True)
    
    provider = build_llm_provider(settings)
    generator = TaxonomyThemeDictionaryGenerator(provider, max_attempts=3, chunk_size=40)
    
    start_time = time.time()
    try:
        print("Starting taxonomy theme generation for 'Witcher 3'...", flush=True)
        # We hook into the planning to see the batches first
        from codeverse_core.data.taxonomy_loader import Language
        batches, skipped = generator._plan_batches(("python", "sql"), None)
        print(f"Total batches planned: {len(batches)}", flush=True)
        
        # Run generation
        dictionary = generator.generate("Witcher 3", "tr")
        duration = time.time() - start_time
        print(f"\nSUCCESS! Generated {len(dictionary.mappings)} mappings in {duration:.2f} seconds.", flush=True)
        
    except Exception as e:
        duration = time.time() - start_time
        print(f"\nFAILED after {duration:.2f} seconds with exception:", flush=True)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
