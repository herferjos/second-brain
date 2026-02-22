import requests
import os

API_URL = "http://localhost:8000/audio"
AUDIO_FILE = "tests/audio_file.mp3"

def test_audio_endpoint():
    # Check if the test file exists
    if not os.path.exists(AUDIO_FILE):
        print(f"❌ Error: The file '{AUDIO_FILE}' does not exist in this directory.")
        print("ℹ️ Please place a real audio file named 'audio_file.mp3' here for testing.")
        return

    print(f"🎧 Sending '{AUDIO_FILE}' to the server...")

    try:
        # Open the file in binary mode
        with open(AUDIO_FILE, "rb") as f:
            files = {"file": (AUDIO_FILE, f, "audio/mpeg")}

            # Send a multipart/form-data POST request
            response = requests.post(API_URL, files=files)

            if response.status_code == 200:
                print("✅ Success:", response.json())
                print("⏳ Check the server terminal to see the transcription progress.")
            else:
                print(f"❌ Failure ({response.status_code}):", response.text)

    except requests.exceptions.ConnectionError:
        print("❌ Connection error: Is the server running on localhost:8000?")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

if __name__ == "__main__":
    test_audio_endpoint()
