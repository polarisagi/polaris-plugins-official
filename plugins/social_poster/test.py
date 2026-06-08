import asyncio
import sys
from src.main import auto_post

async def main():
    print("Starting auto_post test...")
    try:
        # We will test Twitter for this example
        result = await auto_post("twitter", "Hello from Polaris AGI! Testing the new social poster plugin. 🚀", ["/tmp/test_image.jpg"])
        print(f"Result: {result}")
    except Exception as e:
        print(f"Test failed with exception: {e}")

if __name__ == "__main__":
    asyncio.run(main())
