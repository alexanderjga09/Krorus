# Instalar

## Necesitas los siguientes requisitos:
- 🐍 **Python** 3.13.9 [Ir a Descargar](https://www.python.org/downloads/release/python-3139/)
- 💠 **Git** [Ir a Descargar](https://git-scm.com/install/windows)

### Pasos a seguir:

1. Abriendo **PowerShell** o **Git Bash** (No Administrador) tienes que utilizar el siguiente comando, lo que hará es un clon del proyecto que estará conectado con la rama principal (Se hace así para puedas obtener las actualización)
```bash
git clone https://github.com/alexanderjga09/Krorus.git
```

2. Ya dentro proyecto tienes que ejecutar el **start.bat**, lo que hará es chequear sí tienes el Python, pip y la librería **Flet** instala, esa ultima sí no lo está la instalará automaticamente

3. Cuando haya cargado la interfaz grafica del bot, tienes que cargar la carpeta del proyecto y luego rellenar los siguientes campos
  - **Discord Bot Token:** Se obtiene en la pagina [Discord Portal Developer](https://discord.com/developers/home), Tiene acceder en con tu cuenta de Discord e ir a la sección **Aplicaciones** y al boton que dice **Nueva Aplicacion**, una vez la creas te mostra a primera instancia la informacion general de la aplicacion pero donde nos interesa es la seccion **Bot**, Ahi se puede encontrar el **Token** que estamos buscando, para colocar el bot en servidor tiene que ir la sección **OAuth2**, En **OAuth2 URL Generator** tienes que marcar las casillas **bot** y **applications.commands**, En permisos es recomendable que simplemente se seleccione **Administrador** pero si sabes respecto del tema puedes seleccionarlas necesarias y nada más, al final de te generará un link que puedes usar en el navegador de tu preferencia para comenzar el proceso de agregar el bot al servidor.

  - **Groq API Key:** Es la IA que usa el bot en sus funciones más relevantes, para obtener la API de Groq solo tiene que ir a su pagina ([Ir a la pagina de Groq](https://console.groq.com/home)), crearte una cuenta, generar la API y la copias, el plan gratis tiene un limite de 1000 llamadas a la API por dia (los que serian los mensajes/audios), Sí el server tiene mucho trafico, se recomienda las opciones de pago que tenie la plataforma Groq.

  - **VirusTotal API Key:** Está API solamente se le da uso cuando un link que no se encuentra ni en la lista **alert_domains** ni en la lista **whitelist** y sí ese es compartido por un **Protegido** o alguien se lo envia respondiendole o etiquetalos a uno o varios **Protegidos** procederá ha hacer un analisis del link. [Ir a la pagina de VirusTotal](https://www.virustotal.com/gui/my-apikey)

  - **Allowed Guild ID:** Ahí tienes que colocar la ID del servidor donde se va a establecer el bot, Ya colocado eso correctamente el mismo no admitira la entranda o quedar en un server que no coincida con la ID que colocaste.

4. Ya cuando hayan llenado todo los campos, solo te queda a darle a **Configurar**, lo que hará que instalar y acomodar todo para que luego de un rato de espera ya funcione bot. 💞

5. El Bot ya funcionando y en el server correcto, solo tienes que usar el comando **/set-data**, colocarás el canal donde se enviaran todas las alertas y el rol de Protegido. ✅
