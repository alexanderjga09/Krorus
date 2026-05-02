# Krorus — Bot de Moderación para Discord

## ¿Qué es Krorus?

Krorus es un bot de Discord privado orientado a la **protección de menores de edad** dentro de un servidor. Su propósito principal es monitorear la actividad de usuarios marcados con un rol especial llamado **Protegido** — rol que **solo debe asignarse a miembros menores de edad** —, registrar alertas de forma segura y notificar al equipo de staff ante comportamientos sospechosos, sin intervenir públicamente en el chat.

## Aspectos Generales

| Característica | Detalle |
|---|---|
| **Plataforma** | Discord (py-cord) |
| **IA utilizada** | [Groq](https://console.groq.com/) (modelos LLM para análisis de texto y transcripción de audio) |
| **Análisis de enlaces** | [VirusTotal](https://www.virustotal.com/) (escaneo de URLs sospechosas) |
| **Servidor único** | Solo opera en el servidor configurado con el `Allowed Guild ID`. Si se agrega a otro servidor, lo abandona automáticamente. |
| **Visibilidad** | El bot se mantiene en estado **invisible** en Discord. |
| **Persistencia** | Las alertas se almacenan en una cadena de bloques local (`chainlog`) con integridad verificable mediante hashing. |

### ¿Cómo funciona el monitoreo?

> ⚠️ El rol **Protegido** debe asignarse **exclusivamente a miembros menores de edad** del servidor. Es la pieza central sobre la que gira toda la lógica de vigilancia del bot.

El bot procesa cada mensaje del servidor siguiendo esta lógica de prioridad:

1. **Respuesta a un Protegido** — Si alguien responde al mensaje de un menor, el bot analiza el contenido del mensaje (incluyendo posibles enlaces con VirusTotal).
2. **Mención a un Protegido** — Si alguien etiqueta a un menor, el mensaje es analizado de la misma forma.
3. **Mensajes enviados por un Protegido** — Cada mensaje enviado por un menor es analizado en busca de:
   - 🔗 **Enlace sensible** → se verifica el dominio contra la lista de alertas o se escanea con VirusTotal.
   - ❗ **Contenido inapropiado** → la IA (Groq) evalúa si el mensaje tiene conducta inadecuada.
   - 🎙️ **Audios** → se transcriben automáticamente y se analiza el contenido.
   - 📁 **Imágenes, videos y archivos** → se reenvían al canal de staff con una descripción.

> Los mensajes que coincidan con la lista de **palabras ignoradas** (como comandos de bots) no serán procesados, para evitar falsos positivos.

---

## Cómo instalar Krorus

## Requisitos previos:
- 🐍 **Python** 3.13.9 [Ir a Descargar](https://www.python.org/downloads/release/python-3139/)
- 💠 **Git** [Ir a Descargar](https://git-scm.com/install/windows)
- 🦀 **Rust** [Ir a Descargar](https://rust-lang.org/es/tools/install/)

### Pasos a seguir:

1. Abre **PowerShell** o **Git Bash** (sin permisos de administrador) y utiliza el siguiente comando. Esto clonará el proyecto y lo mantendrá conectado a la rama principal para que puedas recibir futuras actualizaciones:
```bash
git clone https://github.com/alexanderjga09/Krorus.git
```

2. Una vez dentro de la carpeta del proyecto, ejecuta el archivo **start.bat**. Este verificará si tienes instalados Python, pip y la librería **Flet**; si esta última no está presente, se instalará automáticamente.

3. Cuando se haya cargado la interfaz gráfica del bot, selecciona la carpeta del proyecto y rellena los siguientes campos:
  - **Discord Bot Token:** Se obtiene en el [Discord Developer Portal](https://discord.com/developers/home). Debes acceder con tu cuenta de Discord, ir a la sección **Applications** y pulsar el botón **New Application**. Una vez creada, en la sección **Bot** encontrarás el **Token**. Para añadir el bot a un servidor, ve a la sección **OAuth2** -> **URL Generator**, marca las casillas **bot** y **applications.commands**. En permisos, se recomienda seleccionar **Administrator**. Al final se generará un enlace que puedes usar en tu navegador para invitar al bot al servidor.

  - **Groq API Key:** Es la IA que usa el bot para sus funciones principales. Para obtenerla, ve a su [página oficial](https://console.groq.com/home), crea una cuenta y genera la API Key. El plan gratuito tiene un límite de 1000 llamadas diarias (mensajes/audios). Si el servidor tiene mucho tráfico, se recomiendan las opciones de pago de Groq.

  - **VirusTotal API Key:** Esta API solo se utiliza cuando se comparte un enlace que no está en las listas **alert_domains** ni **whitelist**, siempre que sea enviado por un **menor (Protegido)** o alguien le responda/etiquete con dicho enlace. En ese caso, se procederá a realizar un análisis del link. [Ir a la página de VirusTotal](https://www.virustotal.com/gui/my-apikey)

  - **Allowed Guild ID:** Aquí debes colocar la ID del servidor donde se establecerá el bot. Una vez configurado, el bot no admitirá la entrada ni permanecerá en ningún servidor que no coincida con esta ID.

4. Cuando hayas llenado todos los campos, haz clic en **Guardar** y luego de un momento a **Configurar**. El programa instalará y preparará todo lo necesario para que, tras un breve momento, el bot comience a funcionar. 💞

5. Con el bot funcionando en el servidor correcto, utiliza el comando **/set-data** para configurar el canal donde se enviarán las alertas y asignar el rol de **Protegido** (el rol que se le dará a los miembros menores de edad). ✅

---

## Comandos

Todos los comandos son **slash commands** (se escriben con `/`). Salvo `/whisper` y `/verify-chain`, todos requieren permisos de **Administrador**.

### ⚙️ Configuración

| Comando | Descripción | Uso | Permisos |
|---|---|---|---|
| `/set-data` | Configura el canal de staff y el rol Protegido (menores de edad). Reinicia el bot al guardar. | `/set-data [#canal] [@rol]` | Administrador |

---

### 🔍 Gestión de Alertas

| Comando | Descripción | Uso | Permisos |
|---|---|---|---|
| `/check-user` | Muestra todas las alertas registradas de un usuario (con paginación). | `/check-user [@usuario]` | Administrador |
| `/pardon` | Perdona una alerta específica por su código, añadiendo un bloque de anulación en la cadena. | `/pardon [código] [motivo]` | Administrador |
| `/list-users` | Lista todos los usuarios que tienen alertas activas, ordenados por cantidad. | `/list-users` | Administrador |
| `/verify-chain` | Verifica la integridad criptográfica de la cadena de alertas. Detecta manipulaciones. | `/verify-chain` | Todos |

---

### 🌐 Gestión de Dominios

| Comando | Descripción | Uso | Permisos |
|---|---|---|---|
| `/append-alertdomain` | Agrega un dominio a la lista de alertas. Cualquier enlace con ese dominio generará una alerta directa. | `/append-alertdomain [dominio]` | Administrador |
| `/remove-alert-domain` | Elimina un dominio de la lista de alertas. | `/remove-alert-domain [dominio]` | Administrador |
| `/view-alert-domains` | Muestra todos los dominios de la lista de alertas con paginación (orden alfabético). | `/view-alert-domains` | Administrador |
| `/append-whitelist` | Agrega un dominio a la lista blanca. Los enlaces con ese dominio no serán analizados. | `/append-whitelist [dominio]` | Administrador |
| `/remove-whitelist-domain` | Elimina un dominio de la lista blanca. | `/remove-whitelist-domain [dominio]` | Administrador |
| `/view-whitelist` | Muestra todos los dominios de la lista blanca con paginación (orden alfabético). | `/view-whitelist` | Administrador |

> **Formato de dominio válido:** `ejemplo.com`, `sub.ejemplo.org`. No incluir `http://` ni rutas.

---

### 🔇 Gestión de Palabras Ignoradas

Útil para ignorar comandos de otros bots (como Mudae) enviados por usuarios Protegidos y evitar falsos positivos.

| Comando | Descripción | Uso | Permisos |
|---|---|---|---|
| `/append-ignoreword` | Añade una o varias palabras/comandos a la lista de ignorados. Separar con comas. | `/append-ignoreword [palabra1, palabra2, ...]` | Administrador |
| `/remove-ignoreword` | Elimina una palabra de la lista de ignorados. | `/remove-ignoreword [palabra]` | Administrador |
| `/view-ignorewords` | Muestra todas las palabras de la lista de ignorados con paginación (orden de inserción). | `/view-ignorewords` | Administrador |
| `/reload-ignorewords` | Recarga la lista de palabras ignoradas desde el archivo (útil si se editó manualmente). | `/reload-ignorewords` | Administrador |

---

### 🔒 Mensajes Secretos

| Comando | Descripción | Uso | Permisos |
|---|---|---|---|
| `/whisper` | Envía un mensaje cifrado por DM a otro usuario. Solo el destinatario puede descifrarlo pulsando un botón (expira en 3 minutos). Si el remitente **o** el destinatario tiene el rol Protegido, el contenido del mensaje es interceptado y enviado al canal de staff automáticamente. | `/whisper [@usuario] [mensaje]` | Todos |
