import io

import discord


async def transcribe_audio(
    self, message: discord.Message, GROQ_CLIENT, member: discord.Member = None
):
    audio_attachment = message.attachments[0]
    # Verifica que sea un formato de audio soportado (mp3, wav, ogg, etc.)
    if any(
        audio_attachment.filename.lower().endswith(fmt)
        for fmt in [".mp3", ".wav", ".ogg", ".m4a", ".flac"]
    ):
        # Lee el archivo de audio de forma asíncrona
        audio_bytes = await audio_attachment.read()
    else:
        return

    try:
        # Prepara el archivo en memoria para enviarlo a Groq
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = audio_attachment.filename  # Asigna un nombre, es requerido

        # Realiza la transcripción de forma asíncrona
        transcription = await GROQ_CLIENT.audio.transcriptions.create(
            file=audio_file,  # El archivo en memoria
            model="whisper-large-v3-turbo",  # Modelo de Groq para transcribir
            response_format="text",  # Formato de la respuesta (texto plano)
        )
        #
        reference = f"Mandado a: {member.mention}" if member else ""

        # Envía la transcripción al canal de staff
        await self._send_alert(
            message,
            "📝 Transcripción de audio",
            f"{reference}\n**Contenido del mensaje de voz:**\n```{transcription}```",
        )

    except Exception as e:
        print(f"Error al transcribir el audio: {e}")
        await self._send_alert(
            message,
            "❌ Error de transcripción",
            f"No se pudo transcribir el audio: {str(e)}",
        )
