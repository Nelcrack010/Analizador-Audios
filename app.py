import os
import re
from flask import Flask, render_template, request, jsonify
from openai import OpenAI

app = Flask(__name__)

# Cliente apuntando a los servidores gratuitos de Groq
client = OpenAI(
    api_key=os.environ.get("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Categorías actualizadas con la petición de tu cliente
MARKET_KEYWORDS = {
    "Precio": ["precio", "costo", "caro", "barato", "oferta", "pago", "dinero", "soles", "dólares"],
    "Calidad": ["calidad", "bueno", "malo", "excelente", "falla", "material"],
    "Servicio": ["atención", "servicio", "soporte", "ayuda", "rápido", "lento"],
    "Cantidad": ["cantidad", "vendido", "unidades", "stock", "total", "volumen"]
}

def generar_resumen_ia(texto):
    """Usa la IA de Groq para leer la transcripción y extraer datos duros."""
    if not texto.strip():
        return "No hay texto para analizar."
    
    prompt = f"""
    Actúa como un analista de datos. Lee la siguiente transcripción de audios de mercado y extrae un resumen ejecutivo. 
    Tu objetivo principal es identificar y listar datos específicos: costos, precios, cantidades vendidas, y métricas importantes.
    Formatea tu respuesta de manera clara usando viñetas. Si no hay números exactos, resume las tendencias de lo que se habló.
    
    Transcripción:
    {texto}
    """
    
    try:
        # Usamos Llama 3 (gratis y súper rápido en Groq) para leer y resumir
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant", 
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error al generar resumen: {str(e)}"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analizar', methods=['POST'])
def analizar_multiples():
    archivos = request.files.getlist('audios')
    if not archivos or archivos[0].filename == '':
        return jsonify({"error": "No seleccionaste archivos"}), 400
    
    transcripciones_totales = []
    conteo_acumulado = {cat: 0 for cat in MARKET_KEYWORDS.keys()}

    for archivo in archivos:
        ruta_archivo = os.path.join(UPLOAD_FOLDER, archivo.filename)
        archivo.save(ruta_archivo)
        
        try:
            # 1. Transcripción de Audio a Texto
            with open(ruta_archivo, "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    model="whisper-large-v3", 
                    file=audio_file,
                    language="es"
                )
            
            texto_final = transcription.text
            transcripciones_totales.append(f"--- {archivo.filename} ---\n{texto_final}")
            
            # 2. Conteo clásico de palabras
            texto_limpio = re.sub(r'[^\w\s]', '', texto_final.lower())
            for categoria, sinonimos in MARKET_KEYWORDS.items():
                for palabra in sinonimos:
                    patron = r'\b' + re.escape(palabra) + r'\b'
                    conteo_acumulado[categoria] += len(re.findall(patron, texto_limpio))
        except Exception as e:
            return jsonify({"error": f"Error procesando {archivo.filename}: {str(e)}"}), 500
        finally:
            if os.path.exists(ruta_archivo):
                os.remove(ruta_archivo)

    # Unimos todo el texto para pasárselo al resumidor
    texto_unido = "\n\n".join(transcripciones_totales)
    
    # 3. Magia de IA: Generar el resumen de datos
    resumen_inteligente = generar_resumen_ia(texto_unido)

    # Cálculo de porcentajes para la gráfica
    total_menciones = sum(conteo_acumulado.values())
    porcentajes = {cat: (round((val / total_menciones) * 100, 2) if total_menciones > 0 else 0) 
                  for cat, val in conteo_acumulado.items()}

    return jsonify({
        "transcripciones": texto_unido,
        "porcentajes": porcentajes,
        "resumen": resumen_inteligente
    })

if __name__ == '__main__':
    app.run(debug=True)