from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.responses import Response
from sarvamai import SarvamAI
from dotenv import load_dotenv
import logging
import os
import base64
import io
import wave 


SARVAM_API_KEY = "sk_ai6o63qj_ThMOAKlHsFVbGaVQdpXvrM1J"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Hello World"}


SUPPORTED_LANGUAGES = [
    "unknown", "hi-IN", "bn-IN", "kn-IN", "ml-IN", 
    "mr-IN", "od-IN", "pa-IN", "ta-IN", "te-IN", "en-IN", "gu-IN"
]


async def sttUsingSarvam(file: UploadFile, language: str) -> str:
    # Set your API key and Sarvam Client
    api_key = SARVAM_API_KEY  # Using the defined API key
    client = SarvamAI(api_subscription_key=api_key)

    try:
        # Save the uploaded file with the correct extension
        filename = file.filename
        if not filename:
            filename = "temp_audio.wav"
        elif not filename.lower().endswith(".wav"):
            filename += ".wav"
        temp_file = os.path.join("temp_uploaded_" + filename)
        with open(temp_file, "wb") as f:
            content = await file.read()
            f.write(content)

        # Reopen the file and send to Sarvam API
        with open(temp_file, "rb") as audio_file:
            response = client.speech_to_text.transcribe(
                file=audio_file,
                model="saarika:v2.5",
                language_code=language
            )
        # Optionally, delete the temp file after use
        try:
            os.remove(temp_file)
        except Exception as cleanup_err:
            print(f"Could not delete temp file: {cleanup_err}")

        if response:
            print("Transcription Success!")
            print("Detected language code:", response.language_code)
            print("Detected transcript:", response.transcript)
            return response.transcript
        else:
            print("No response received from the API.")
            return "No response received from the API."
    except Exception as e:
        print("Exception occurred:", str(e))
        return f"Exception occurred: {str(e)}"
    

async def callLLMUsingSarvam(textParam: str) -> str:
    client = SarvamAI(api_subscription_key=SARVAM_API_KEY)
    print("User prompt:", textParam)
    try:
        llm_response = client.chat.completions(
            messages=[
                {"role": "user", "content": textParam}
            ]
        )
        reply = llm_response.choices[0].message.content
        print("Sarvam LLM reply:", reply)
        return reply
    except Exception as e:
        print("Error calling Sarvam LLM:", str(e))
        raise e

def clean_text_for_tts(text: str) -> str:
    # Remove markdown formatting
    text = text.replace('**', '')
    text = text.replace('###', '')
    text = text.replace('🇮🇳', '')
    
    # Remove bullet points and clean up
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        # Remove markdown bullet points and clean up
        line = line.strip()
        if line.startswith('- '):
            line = line[2:]
        if line:  # Only add non-empty lines
            cleaned_lines.append(line)
    
    return ' '.join(cleaned_lines)

async def callTextToSpeechUsingSarvam(replyParam: str, language: str) -> bytes:
    client = SarvamAI(api_subscription_key=SARVAM_API_KEY)
    try:
        # Clean the text before sending to TTS
        cleaned_text = clean_text_for_tts(replyParam)
        print("Cleaned text for TTS:", cleaned_text)
        
        tts_response = client.text_to_speech.convert(
            text=cleaned_text,
            target_language_code=language,
            speaker="manisha"  
        )
        base64_audio = tts_response.audios[0]
        audio_bytes = base64.b64decode(base64_audio)
        
        # Print audio info for debugging
        print(f"Audio bytes received: {len(audio_bytes)} bytes")
        return audio_bytes
    except Exception as e:
        print("TTS Error:", str(e))
        raise e

def pcm_to_wav(pcm_bytes: bytes, sample_rate=16000, num_channels=1, sample_width=2) -> bytes:
    """Convert PCM audio bytes to WAV format."""
    print(f"Converting {len(pcm_bytes)} bytes of PCM data to WAV format")
    try:
        with io.BytesIO() as wav_io:
            with wave.open(wav_io, 'wb') as wf:
                wf.setnchannels(num_channels)
                wf.setsampwidth(sample_width)
                wf.setframerate(sample_rate)
                wf.writeframes(pcm_bytes)
            wav_bytes = wav_io.getvalue()
            print(f"Successfully created WAV file: {len(wav_bytes)} bytes")
            return wav_bytes
    except Exception as e:
        print(f"Error converting PCM to WAV: {str(e)}")
        # If conversion fails, try to return the original bytes
        # The API might already be returning WAV format
        print("Returning original audio bytes")
        return pcm_bytes

@app.post("/upload-audio/")
async def upload_audio(file: UploadFile = File(...), language: str = Form(...)):
    if language not in SUPPORTED_LANGUAGES:
        return {"error": f"Unsupported language code. Please use one of: {', '.join(SUPPORTED_LANGUAGES)}"}
    
    try:
        # Step 1: Convert speech to text
        text = await sttUsingSarvam(file, language)
        if text.startswith("Exception occurred:"):
            return {"error": text}
            
        # Step 2: Get LLM response
        reply = await callLLMUsingSarvam(text)
        
        # Step 3: Convert response to speech
        audio_bytes = await callTextToSpeechUsingSarvam(reply, language)
        
        # Save raw bytes for debugging
        debug_file = "debug_output.bin"
        with open(debug_file, "wb") as f:
            f.write(audio_bytes)
        
        # Create a WAV file in memory
        wav_bytes = pcm_to_wav(audio_bytes)
        
        # Save WAV file for debugging
        with open("debug_output.wav", "wb") as f:
            f.write(wav_bytes)
        
        # Create a BytesIO object for streaming
        audio_stream = io.BytesIO(wav_bytes)
        
        # Return StreamingResponse instead of Response
        return StreamingResponse(
            audio_stream,
            media_type="audio/wav",
            headers={
                "Accept-Ranges": "bytes",
                "Content-Disposition": 'attachment; filename="output.wav"'  # Changed to attachment for download
            }
        )
    except Exception as e:
        print(f"Error in upload_audio: {str(e)}")
        return {"error": str(e)}

    
