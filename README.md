# Cómo instalar Krorus

## Requisitos previos:
- 🐍 **Python** 3.13.9 [Ir a Descargar](https://www.python.org/downloads/release/python-3139/)
- 💠 **Git** [Ir a Descargar](https://git-scm.com/install/windows)

### Pasos a seguir:

1. Abre **PowerShell** o **Git Bash** (sin permisos de administrador) y utiliza el siguiente comando. Esto clonará el proyecto y lo mantendrá conectado a la rama principal para que puedas recibir futuras actualizaciones:
```bash
git clone https://github.com/alexanderjga09/Krorus.git
```

2. Una vez dentro de la carpeta del proyecto, ejecuta el archivo **start.bat**. Este verificará si tienes instalados Python, pip y la librería **Flet**; si esta última no está presente, se instalará automáticamente.

3. Cuando se haya cargado la interfaz gráfica del bot, selecciona la carpeta del proyecto y rellena los siguientes campos:
  - **Discord Bot Token:** Se obtiene en el [Discord Developer Portal](https://discord.com/developers/home). Debes acceder con tu cuenta de Discord, ir a la sección **Applications** y pulsar el botón **New Application**. Una vez creada, en la sección **Bot** encontrarás el **Token**. Para añadir el bot a un servidor, ve a la sección **OAuth2** -> **URL Generator**, marca las casillas **bot** y **applications.commands**. En permisos, se recomienda seleccionar **Administrator**. Al final se generará un enlace que puedes usar en tu navegador para invitar al bot al servidor.

  - **Groq API Key:** Es la IA que usa el bot para sus funciones principales. Para obtenerla, ve a su [página oficial](https://console.groq.com/home), crea una cuenta y genera la API Key. El plan gratuito tiene un límite de 1000 llamadas diarias (mensajes/audios). Si el servidor tiene mucho tráfico, se recomiendan las opciones de pago de Groq.

  - **VirusTotal API Key:** Esta API solo se utiliza cuando se comparte un enlace que no está en las listas **alert_domains** ni **whitelist**, siempre que sea enviado por un **Protegido** o alguien le responda/etiquete con dicho enlace. En ese caso, se procederá a realizar un análisis del link. [Ir a la página de VirusTotal](https://www.virustotal.com/gui/my-apikey)

  - **Allowed Guild ID:** Aquí debes colocar la ID del servidor donde se establecerá el bot. Una vez configurado, el bot no admitirá la entrada ni permanecerá en ningún servidor que no coincida con esta ID.

4. Cuando hayas llenado todos los campos, haz clic en **Configurar**. El programa instalará y preparará todo lo necesario para que, tras un breve momento, el bot comience a funcionar. 💞

5. Con el bot funcionando en el servidor correcto, utiliza el comando **/set-data** para configurar el canal donde se enviarán las alertas y asignar el rol de Protegido. ✅
