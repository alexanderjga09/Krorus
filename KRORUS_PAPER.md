# Krorus — Paper Técnico

> **Versión:** 1.0 | **Última actualización:** Junio 2026  
> **Autor:** AlexanderJGA  
> **Repositorio:** https://github.com/alexanderjga09/Krorus

---

## Índice

1. [Resumen Ejecutivo](#1-resumen-ejecutivo)
2. [Arquitectura General](#2-arquitectura-general)
3. [Flujo de Datos](#3-flujo-de-datos)
4. [Módulos del Sistema](#4-módulos-del-sistema)
5. [Sistema de Análisis con IA (Groq)](#5-sistema-de-análisis-con-ia-groq)
6. [Cadena de Bloques de Alertas (ChainLog)](#6-cadena-de-bloques-de-alertas-chainlog)
7. [Sistema de Cifrado (/whisper)](#7-sistema-de-cifrado-whisper)
8. [Análisis de URLs y Dominios](#8-análisis-de-urls-y-dominios)
9. [Análisis de Metadatos EXIF](#9-análisis-de-metadatos-exif)
10. [Transcripción de Audio](#10-transcripción-de-audio)
11. [Sistema de Rate Limiting y Pool de Keys](#11-sistema-de-rate-limiting-y-pool-de-keys)
12. [Sistema de Buffer y Lote de Mensajes](#12-sistema-de-buffer-y-lote-de-mensajes)
13. [Seguridad y Permisos](#13-seguridad-y-permisos)
14. [Infraestructura Técnica](#14-infraestructura-técnica)
15. [Preguntas Frecuentes](#15-preguntas-frecuentes)

---

## 1. Resumen Ejecutivo

**Krorus** es un bot de Discord privado diseñado para la **protección de menores de edad** dentro de un servidor. Su propósito es monitorear la actividad de usuarios marcados con un rol especial llamado **Protegido** — asignado exclusivamente a miembros menores de edad —, registrar alertas de forma segura y notificar al equipo de staff ante comportamientos sospechosos, sin intervenir públicamente en el chat.

### Características Principales

| Característica | Detalle |
|---|---|
| **Plataforma** | Discord (py-cord 2.7.2) |
| **IA utilizada** | Groq (Llama 3.3 70B para análisis + Whisper para audio) |
| **Análisis de URLs** | VirusTotal API + listas locales de dominios |
| **Servidor único** | Solo opera en el servidor configurado (`Allowed Guild ID`) |
| **Visibilidad** | Invisible en Discord (estado offline) |
| **Persistencia** | Cadena de bloques local con integridad verificable (SHA-256) |
| **Interfaz** | GUI de escritorio (Flet) para configuración y gestión |

### Modelo de Amenaza

Krorus opera bajo el principio de que **el staff del servidor es confiable**. El bot:
- Intercepta mensajes privados (`/whisper`) cuando un menor está involucrado.
- Almacena claves privadas RSA sin cifrar en el servidor (necesario por diseño).
- Envía alertas solo a un canal privado de staff.
- Nunca publica información en canales públicos.

---

## 2. Arquitectura General

### Estructura del Proyecto

```
Krorus/
├── main.py                    # Punto de entrada
├── setup_gui.py               # Lanzador de la GUI
├── start.bat                  # Lanzador Windows
│
├── scripts/                   # Código fuente del bot
│   ├── core.py                # Clase principal Krorus (Bot)
│   ├── cogs/                  # Comandos slash de Discord
│   │   ├── append_alertdomain.py
│   │   ├── append_ignoreword.py
│   │   ├── append_whitelist.py
│   │   ├── check_user.py
│   │   ├── exif_check.py
│   │   ├── health.py
│   │   ├── list_users.py
│   │   ├── set_data.py
│   │   └── whisper.py
│   └── modules/               # Lógica central
│       ├── message.py         # Análisis de mensajes + RateLimiter
│       ├── chainlog.py        # Wrapper de la cadena de bloques
│       ├── database.py        # SQLite (configuración)
│       ├── rsa.py             # Cifrado híbrido AES+RSA
│       ├── exif_checker.py    # Análisis EXIF
│       ├── misconduct_cache.py # Caché de clasificaciones IA
│       ├── pagination.py      # Paginador de Discord
│       ├── code.py            # Generador de códigos de alerta
│       └── utils.py           # Utilidades generales
│
├── crates/                    # Extensiones nativas Rust
│   ├── chainlog_rs/           # Cadena de bloques (SHA-256)
│   └── exif_rs/               # Extracción EXIF rápida
│
├── gui/                       # Interfaz gráfica de escritorio
│   ├── core.py                # Widgets, consola, logging
│   ├── ui.py                  # Layout, pestañas, selectors
│   └── actions.py             # Setup, start/stop, git, backups
│
├── tests/                     # Suite de pruebas
├── data/                      # Datos en runtime
└── .env                       # Secrets (TOKEN, API keys)
```

### Diagrama de Componentes

```
┌─────────────────────────────────────────────────────┐
│                    Discord API                       │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│              Krorus (Bot Principal)                  │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │   Cogs      │  │   Modules    │  │   Crates   │ │
│  │ (Comandos)  │  │  (Lógica)    │  │  (Rust)    │ │
│  └──────┬──────┘  └──────┬───────┘  └─────┬──────┘ │
│         │                │                 │         │
│         ▼                ▼                 ▼         │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │ set_data    │  │ message.py   │  │ chainlog_rs│ │
│  │ check_user  │  │ rsa.py       │  │ exif_rs    │ │
│  │ whisper     │  │ exif_checker │  └────────────┘ │
│  │ health      │  │ database.py  │                  │
│  │ ...         │  │ cache.py     │                  │
│  └─────────────┘  └──────┬───────┘                  │
│                          │                           │
└──────────────────────────┼───────────────────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │  Groq    │ │VirusTotal│ │  SQLite  │
        │  API     │ │   API    │ │   DB     │
        └──────────┘ └──────────┘ └──────────┘
```

---

## 3. Flujo de Datos

### Proceso de Análisis de un Mensaje

Cuando el bot recibe un mensaje en Discord, se ejecuta el siguiente proceso:

```
Mensaje Recibido
       │
       ▼
┌──────────────────┐
│ Filtros Iniciales│  ¿Es bot? ¿Es DM? ¿Guild correcto?
│                  │  ¿Está en rate limit?
└────────┬─────────┘
         │ Pass
         ▼
┌──────────────────┐
│ ¿Es respuesta a  │
│ mensaje protegido?│──SÍ──► Analizar mensaje referenciado
│                  │        (adjuntos, URLs, audio, EXIF)
└────────┬─────────┘
         │ NO
         ▼
┌──────────────────┐
│ ¿Menciona a un   │
│ protegido?       │──SÍ──► Analizar mensaje con menciones
│                  │        (adjuntos, URLs, audio, EXIF)
└────────┬─────────┘
         │ NO
         ▼
┌──────────────────┐
│ ¿Autor es        │
│ protegido?       │──SÍ──► Procesar según config:
│                  │        - URLs → VirusTotal/listas
│                  │        - Audio → Transcribir
│                  │        - Imágenes → EXIF + reenviar
│                  │        - Texto → Buffer para Groq
└────────┬─────────┘
         │ NO
         ▼
┌──────────────────┐
│ Procesar adjuntos│  Solo URLs, media, audio (sin análisis
│ (si hay buffer)  │  de misconduct para no-protegidos)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Flush del Buffer │  Se combinan mensajes del mismo usuario
│                  │  en los últimos 60 segundos
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Análisis Groq    │  Texto combinado → Llama 3.3 70B
│ (Misconduct)     │  Respuesta: "True" o "False"
└────────┬─────────┘
         │ "True"
         ▼
┌──────────────────┐
│ Generar Alerta   │  Código único → ChainLog → Canal staff
│                  │  Embed con detalles del usuario
└──────────────────┘
```

### Prioridad de Procesamiento

El bot procesa los mensajes en este orden de prioridad:

1. **Respuesta a un protegido** → Se analiza el contenido del mensaje respondido
2. **Mención a un protegido** → Se analiza el contenido del mensaje
3. **Mensaje enviado por un protegido** → Se analiza en busca de:
   - Enlaces sensibles (alert_domains o VirusTotal)
   - Contenido inapropiado (Groq IA)
   - Audios (transcripción Groq Whisper)
   - Imágenes/videos/archivos (reenvío al staff)
   - Metadatos EXIF (GPS, serial de cámara, etc.)

---

## 4. Módulos del Sistema

### 4.1 `message.py` — Corre del Análisis

Este es el módulo más importante del bot. Contiene:

- **`Message`**: Clase que envuelve un `discord.Message` de Discord
- **`GroqRateLimiter`**: Gestor de rate limiting con pool de keys
- **`groq_rate_limiter`**: Instancia singleton del rate limiter
- **`MisconductPrompt`**: Prompt para detección de conducta inapropiada

Funciones principales:

```python
# Análisis de URLs
Message.CheckAndAlert()  # Escanea URLs con listas locales y VirusTotal

# Análisis de conducta
Message.Misconduct()     # Evalúa texto con Groq (True/False)

# Transcripción
Message.transcribe_audio()  # Transcribe audio con Groq Whisper

# EXIF
Message.check_exif_sensible()  # Analiza metadatos de imágenes
```

### 4.2 `database.py` — Persistencia SQLite

Almacena la configuración del servidor en un solo registro:

```sql
CREATE TABLE settings (
    id INTEGER PRIMARY KEY,
    staff_channel_id TEXT,
    protected_role_id TEXT
);
```

Características:
- **Backups automáticos**: Máximo 5 backups con timestamps
- **Escritura atómica**: Usa transacciones SQLite
- **Restauración**: `restore_latest_backup()` desde el backup más reciente

### 4.3 `rsa.py` — Cifrado Híbrido

Implementa cifrado híbrido **AES-256-GCM + RSA-OAEP** para `/whisper`:

```
Mensaje original
       │
       ▼
┌──────────────────┐
│ Generar clave AES│  Clave aleatoria de 256 bits
│ aleatoria        │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Cifrar mensaje   │  AES-256-GCM (confidencialidad + integridad)
│ con AES          │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Cifrar clave AES │  RSA-OAEP con clave pública del destinatario
│ con RSA          │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Formato final:   │  base64(rsa_encrypted_key || nonce || aes_ciphertext)
│ base64           │
└──────────────────┘
```

### 4.4 `chainlog.py` — Cadena de Bloques

Wrapper Python del crate Rust `chainlog_rs`. Cada llamada crea una **nueva instancia** (diseño deliberado):

```python
def get_chain_log() -> ChainLog:
    return ChainLog(str(_CHAIN_FILE))  # Siempre lee desde disco
```

Esto garantiza que ediciones externas al archivo sean detectadas por la verificación de integridad.

---

## 5. Sistema de Análisis con IA (Groq)

### Modelo Utilizado

- **Modelo de texto**: `llama-3.3-70b-versatile` (70B parámetros)
- **Modelo de audio**: `whisper-large-v3-turbo`
- **Temperatura**: 0.0 (respuestas deterministas)
- **Timeout**: 10 segundos por petición

### Prompt de Moderación

El prompt le indica a la IA que actúe como "Moderador de Contenido" y evalúe si el texto contiene:

- Insultos, acoso o bullying
- Contenido sexual o sugestivo
- Grooming o conducta depredadora
- Incitación al odio o violencia
- Doxing o información personal
- Evasión mediante leetspeak, espaciado o roleplay

### Respuesta

La IA responde exclusivamente `True` o `False`:
- **`True`**: El texto contiene conducta inapropiada → Se genera alerta
- **`False`**: El texto es seguro → No se genera alerta

### Caché de Clasificaciones

```python
# Caché LRU en memoria
_MISCONDUCT_CACHE: dict[str, dict] = {}  # SHA256 → {result, timestamp}
_MISCONDUCT_CACHE_MAX = 512              # Entradas máximas
_MISCONDUCT_CACHE_TTL = 300              # TTL: 5 minutos
```

El caché almacena resultados keyed por SHA-256 del texto normalizado, evitando llamadas repetidas a la API para el mismo contenido.

---

## 6. Cadena de Bloques de Alertas (ChainLog)

### Diseño

ChainLog implementa una **blockchain local** para garantizar la integridad de las alertas:

```
Bloque 0 (Génesis)          Bloque 1 (Alerta)           Bloque 2 (Indulto)
┌─────────────────┐        ┌─────────────────┐        ┌─────────────────┐
│ index: 0        │        │ index: 1        │        │ index: 2        │
│ timestamp: ...  │        │ timestamp: ...  │        │ timestamp: ...  │
│ data: "genesis" │        │ data: {...}     │        │ data: {...}     │
│ prev: "0"*64    │        │ prev: hash[0]   │        │ prev: hash[1]   │
│ hash: sha256()  │        │ hash: sha256()  │        │ hash: sha256()  │
│ type: genesis   │        │ type: alert     │        │ type: pardon    │
└─────────────────┘        └─────────────────┘        └─────────────────┘
```

### Estructura de un Bloque de Alerta

```json
{
    "index": 1,
    "timestamp": "2026-06-29T15:30:00",
    "data": {
        "user_id": "123456789",
        "code": "a1b2c3d4e5",
        "reason": "Insulto detectado por IA",
        "jump_url": "https://discord.com/channels/..."
    },
    "previous_hash": "0000...0000",
    "hash": "abc123...",
    "block_type": "alert"
}
```

### Estructura de un Bloque de Indulto

```json
{
    "index": 2,
    "timestamp": "2026-06-29T16:00:00",
    "data": {
        "original_index": 1,
        "moderator_id": "987654321",
        "reason": "Falso positivo, era broma entre amigos"
    },
    "previous_hash": "abc123...",
    "hash": "def456...",
    "block_type": "pardon"
}
```

### Verificación de Integridad

El comando `/verify-chain` ejecuta:

```rust
// En Rust (chainlog_rs)
fn verify_chain(&self) -> bool {
    let mut prev_hash = "0".repeat(64);  // Génesis
    for block in &self.blocks {
        let computed = compute_hash(block.index, &block.timestamp, &block.data, &prev_hash);
        if computed != block.hash {
            return false;  // ¡Cadena manipulada!
        }
        prev_hash = block.hash.clone();
    }
    true
}
```

### Modelo de Indulto

Las alertas **nunca se eliminan**. Un indulto agrega un nuevo bloque que referencia la alerta original. El comando `/list-users` muestra solo alertas activas (sin indulto).

---

## 7. Sistema de Cifrado (/whisper)

### Flujo Completo

```
Usuario A envía /whisper @UsuarioB "mensaje secreto"
       │
       ▼
┌──────────────────┐
│ ¿A o B tienen    │
│ rol Protegido?   │──SÍ──► Enviar contenido al canal staff
└────────┬─────────┘        (intercepción antes de cifrar)
         │ NO
         ▼
┌──────────────────┐
│ Obtener clave    │
│ pública de B     │  from data/keysDB.json
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Cifrar mensaje   │  AES-256-GCM + RSA-OAEP
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Enviar DM a B    │  Botón "Descifrar" (expira 3 min)
│ con ciphertext   │
└────────┬─────────┘
         │ B presiona botón
         ▼
┌──────────────────┐
│ Descifrar con    │
│ clave privada de B│
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Mostrar mensaje  │  Si A o B es protegido → alerta al staff
└──────────────────┘
```

### Modelo de Amenaza

> **Importante**: El cifrado protege contra **otros usuarios de Discord**, no contra el operador del bot.

- Las claves privadas RSA se almacenan **sin cifrar** en `data/keysDB.json`.
- Esto es **necesario por diseño** para que el staff pueda interceptar whispers que involucran a un menor.
- Cualquier persona con acceso al sistema de archivos puede descifrar todos los whispers.
- `data/keysDB.json` está excluido de git y se intenta aplicar permisos `0600`.

---

## 8. Análisis de URLs y Dominios

### Sistema de Tres Niveles

```
URL detectada en mensaje
       │
       ▼
┌──────────────────┐
│ ¿Dominio en      │
│ whitelist.json?  │──SÍ──► OMITIR (no analizar)
└────────┬─────────┘
         │ NO
         ▼
┌──────────────────┐
│ ¿Dominio en      │
│ alert_domains?   │──SÍ──► ALERTA INMEDIATA
└────────┬─────────┘        (sin VirusTotal)
         │ NO
         ▼
┌──────────────────┐
│ ¿Es invite de    │
│ Discord?         │──SÍ──► ALERTA INMEDIATA
└────────┬─────────┘
         │ NO
         ▼
┌──────────────────┐
│ VirusTotal API   │  Escaneo con semáforo (4 concurrencia)
│ (rate limited)   │  Cooldown global 60s en 429
└──────────────────┘
```

### Listas de Dominios

| Lista | Archivo | Propósito |
|-------|---------|-----------|
| **Alertas** | `data/alert_domains.json` | Dominios que siempre generan alerta |
| **Whitelist** | `data/whitelist.json` | Dominios excluidos de análisis |

### Comandos de Gestión

```
/append-alertdomain [dominio]      # Agregar a lista de alertas
/remove-alert-domain [dominio]     # Remover de lista de alertas
/view-alert-domains                # Ver todas las alertas

/append-whitelist [dominio]        # Agregar a whitelist
/remove-whitelist-domain [dominio] # Remover de whitelist
/view-whitelist                    # Ver whitelist
```

---

## 9. Análisis de Metadatos EXIF

### Implementación Dual

Krorus implementa extracción EXIF en dos lenguajes:

1. **Rust (`exif_rs`)**: Implementación principal usando `kamadak-exif`. Máximo rendimiento sin bloquear el GIL de Python.
2. **Python (PIL/Pillow)**: Fallback si el crate Rust no está compilado.

### Campos Detectados

| Riesgo | Campos | Ejemplo |
|--------|--------|---------|
| **Alto** | GPS (lat/lon), Serial de cámara, OwnerName | `GPS: 40.7128, -74.0060` |
| **Medio** | Modelo de cámara, Software, Fecha de captura | `Canon EOS R5` |

### Proceso

```
Imagen recibida
       │
       ▼
┌──────────────────┐
│ Intentar exif_rs │  Rust (rápido, sin GIL)
│ (crate nativo)   │
└────────┬─────────┘
         │ Falló
         ▼
┌──────────────────┐
│ Fallback PIL     │  Python (más lento)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Evaluar campos   │
│ sensibles        │
└────────┬─────────┘
         │ Riesgo alto
         ▼
┌──────────────────┐
│ Generar alerta   │  Incluye GPS, serial, etc.
│ inmediata        │  al canal de staff
└──────────────────┘
```

### Análisis de ZIPs

El sistema también analiza archivos ZIP, extrayendo y verificando EXIF de cada imagen contenida.

---

## 10. Transcripción de Audio

### Modelo

- **API**: Groq Whisper (`whisper-large-v3-turbo`)
- **Proceso**: Audio → Transcripción → Análisis de texto con Llama 3.3 70B

### Flujo

```
Audio de Discord (.ogg, .mp3, etc.)
       │
       ▼
┌──────────────────┐
│ Descargar audio  │  bytes del attachment
│ a archivo temporal│
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Enviar a Groq    │  whisper-large-v3-turbo
│ Whisper API      │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Texto transcrito │
│ → Misconduct()   │  Análisis con Llama 3.3 70B
└──────────────────┘
```

---

## 11. Sistema de Rate Limiting y Pool de Keys

### Arquitectura del RateLimiter

```python
class GroqRateLimiter:
    """Sala de espera con pool de keys API"""
    
    # Configuración por defecto
    max_calls = 25        # Llamadas por ventana
    window = 60.0         # Ventana de 60 segundos
    max_waiting = 40      # Cola máxima de espera
    overflow_reserve = 5  # Slots extra para overflow
```

### Selección de Key

```python
def _best_key(self, now: float) -> tuple[int, float]:
    """Selecciona la key con menor tiempo de espera"""
    best_idx = 0
    best_wait = float("inf")
    for i in range(len(self._key_states)):
        w = self._waits(now, i)  # Calcula espera para cada key
        if w < best_wait:
            best_wait = w
            best_idx = i
    return best_idx, best_wait
```

### Sistema de Overflow

Cuando la cola está llena (>= 40 esperando):

```
Request nueva
       │
       ▼
┌──────────────────┐
│ Cola llena       │
│ (40 esperando)   │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Guardar en       │  data/overflow_queue.json
│ overflow_queue   │  (archivo JSON persistente)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Procesar cuando  │  Drain automático después
│ haya turnos      │  de flush del buffer
└──────────────────┘
```

### Límites por Key (Free Tier Groq)

| Modelo | RPM | RPD | TPM | TPD |
|--------|-----|-----|-----|-----|
| llama-3.3-70b-versatile | 30 | 1,000 | 12,000 | 100,000 |
| whisper-large-v3-turbo | 20 | 2,000 | - | - |

Con 3 keys, el pool ofrece **3x estos límites**.

---

## 12. Sistema de Buffer y Lote de Mensajes

### Propósito

El buffer acumula mensajes cortos del mismo usuario para:
1. Detectar insultos escritos en múltiples mensajes
2. Reducir llamadas a la API de Groq
3. Capturar mensajes previos no procesados (lookback)

### Mecanismo

```
Usuario A escribe: "Hola"
       │
       ▼
┌──────────────────┐
│ Agregar a buffer │  _msg_buffer[channel][author] = [msgs]
│ del canal        │
└────────┬─────────┘
         │
         ▼
Usuario B escribe: "¿Qué tal?"
       │
       ▼
┌──────────────────┐
│ Flush del buffer │  ¿Otro usuario habló? → FLUSH
│ de A             │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Combinar msgs   │  "Hola" → análisis individual
│ de A             │  (B no estaba en el buffer)
└──────────────────┘
```

### Lookback

Cuando se procesa una respuesta/mención, el bot busca mensajes recientes (60s) del autor que no fueron capturados:

```python
async def _lookback(self, channel, author, since_dt):
    """Busca mensajes no procesados de un usuario en los últimos 60s"""
    async for msg in channel.history(after=since_dt, limit=20):
        if msg.author == author and msg.id not in self._processed_ids:
            # Procesar adjuntos, URLs, audio
```

---

## 13. Seguridad y Permisos

### Aislamiento de Guild

```python
@commands.Cog.listener()
async def on_ready(self):
    # Verificar guild permitido
    if str(self.guild.id) != ALLOWED_GUILD_ID:
        await self.guild.leave()
        # Notificar al owner por DM
```

### Permisos de Comandos

| Comando | Requiere Admin | Disponible para |
|---------|----------------|-----------------|
| `/set-data` | Sí | Staff |
| `/reload-config` | Sí | Staff |
| `/check-user` | Sí | Staff |
| `/pardon` | Sí | Staff |
| `/list-users` | Sí | Staff |
| `/verify-chain` | No | Todos |
| `/whisper` | No | Todos |
| `/check-exif` | Sí | Staff |

### Normalización Anti-Evasión

El texto se normaliza antes de enviarlo a Groq:

```python
def _normalize_for_groq(text: str) -> str:
    # Eliminar caracteres invisibles
    text = unicodedata.normalize("NFC", text)
    # Eliminar espacios de ancho cero
    text = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', text)
    # Eliminar marcas bidireccionales
    text = re.sub(r'[\u202a-\u202e\u2066-\u2069]', '', text)
    return text.strip()
```

---

## 14. Infraestructura Técnica

### Dependencias Principales

| Dependencia | Versión | Propósito |
|-------------|---------|-----------|
| **py-cord** | 2.7.2 | Wrapper de Discord API |
| **groq** | 1.2.0 | Cliente Groq (LLM + Whisper) |
| **cryptography** | 46.0.7 | RSA + AES-GCM |
| **pillow** | 12.2.0 | EXIF fallback (PIL) |
| **aiohttp** | - | HTTP async (VirusTotal) |
| **python-dotenv** | - | Carga de .env |
| **flet** | 0.84.0 | GUI de escritorio |

### Extensiones Rust

| Crate | Dependencias | Propósito |
|-------|-------------|-----------|
| **chainlog_rs** | pyo3, sha2, serde, chrono | Cadena de bloques SHA-256 |
| **exif_rs** | pyo3, kamadak-exif | Extracción EXIF rápida |

### Perfil de Compilación Rust

```toml
[profile.release]
lto = true
opt-level = 3
codegen-units = 1
strip = true
```

### Archivos de Datos en Runtime

| Archivo | Propósito | Persistente |
|---------|-----------|-------------|
| `data/settings.db` | Configuración SQLite | Sí |
| `data/logs.json` | Cadena de bloques | Sí |
| `data/keysDB.json` | Claves RSA por usuario | Sí |
| `data/bot_config.json` | Toggles de funciones | Sí |
| `data/alert_domains.json` | Dominios de alerta | Sí |
| `data/whitelist.json` | Dominios whitelist | Sí |
| `data/ignorewords.json` | Palabras ignoradas | Sí |
| `data/misconduct_cache.json` | Caché de clasificaciones | Sí |
| `data/overflow_queue.json` | Cola de overflow | Sí |
| `data/krorus.log` | Log rotativo | Sí |

---

## 15. Preguntas Frecuentes

### ¿Krorus es un bot público?

**No.** Krorus es un bot **privado** que solo opera en un servidor específico. Si se agrega a otro servidor, lo abandona automáticamente y notifica al owner por DM.

### ¿Puedo usar Krorus en mi servidor?

Sí, pero debes tener en cuenta:
- Necesitas una cuenta de Groq (gratuita o de pago)
- Necesitas una cuenta de VirusTotal (opcional pero recomendada)
- El bot es **invisible** — no aparece en la lista de miembros
- Las alertas se envían a un canal privado de staff

### ¿Cuánto cuesta usar Groq?

El plan gratuito de Groq ofrece:
- 30 requests/minuto
- 1,000 requests/día (para llama-3.3-70b-versatile)
- 12,000 tokens/minuto

Con 3 keys API, estos límites se **triplican**. Para servidores con mucho tráfico, se recomienda el plan de pago.

### ¿Es seguro el cifrado de /whisper?

El cifrado protege contra **otros usuarios de Discord**, no contra el operador del bot. Las claves privadas RSA se almacenan sin cifrar en el servidor (necesario para que el staff pueda interceptar whispers de menores). Si alguien tiene acceso al sistema de archivos, puede descifrar los whispers.

### ¿Cómo funciona la verificación de integridad?

El comando `/verify-chain` recorre toda la cadena de bloques, recalculando el hash SHA-256 de cada bloque y verificando que cada hash referencie correctamente al anterior. Si el archivo `logs.json` es editado externamente, la verificación falla.

### ¿Qué pasa si Groq se cae?

El bot sigue funcionando. Si Groq no está disponible:
- El análisis de misconduct se desactiva temporalmente
- Las URLs y EXIF se siguen procesando
- Los mensajes se almacenan en la cola de overflow

### ¿Puedo personalizar el comportamiento del bot?

Sí, desde la GUI (pestaña "Funciones"):
- Activar/desactivar funciones individuales
- Cambiar configuración sin reiniciar (`/reload-config`)
- Gestionar listas de dominios y palabras ignoradas

### ¿Cómo se actualiza el bot?

Desde la GUI:
1. Clic en "Actualizar Proyecto" (ícono de actualización)
2. El bot ejecuta `git pull` automáticamente
3. Se recompilan las dependencias y extensiones Rust
4. Se reinicia el bot

### ¿Los datos están respaldados?

Sí:
- La base de datos SQLite tiene **backups automáticos** (máximo 5)
- La cadena de bloques es **append-only** (nunca se borran alertas)
- La GUI permite crear backups manuales y restaurar

### ¿Puedo ver las alertas de un usuario?

Sí, con el comando `/check-user @usuario`. Muestra:
- Todas las alertas activas
- Fechas, códigos y razones
- Opción de indultar con `/pardon`

---

## Conclusión

Krorus representa un enfoque técnico robusto para la protección de menores en Discord. Combina:

- **Inteligencia Artificial** (Groq) para detección de conducta inapropiada
- **Cadena de bloques** para integridad criptográfica de alertas
- **Cifrado híbrido** para comunicación privada segura
- **Análisis multiventana** (URLs, EXIF, audio, texto)
- **Rate limiting inteligente** con pool de keys
- **Interfaz gráfica** para gestión fácil

El diseño prioriza la **seguridad de los menores** sobre la privacidad de los usuarios adultos, con transparencia documentada sobre las implicaciones de seguridad del modelo.

---

*Krorus — Protegiendo menores en Discord con tecnología de vanguardia.*
