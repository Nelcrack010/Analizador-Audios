import os
import re
from flask import Flask, render_template, request, jsonify
from openai import OpenAI

app = Flask(__name__)

# Render leerá la clave desde las Variables de Entorno que configuraste
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Categorías para tu estudio de mercado
MARKET_KEYWORDS = {
    "Precio": ["precio", "costo", "caro", "barato", "oferta", "pago", "dinero"],
    "Calidad": ["calidad", "bueno", "malo", "excelente", "falla", "material"],
    "Servicio": ["atención", "servicio", "soporte", "ayuda", "rápido", "lento"],
    "Competencia": ["competencia", "otros", "marca", "diferente", "mejor"]
}

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
            # Llamada a la API de OpenAI para transcripción rápida
            with open(ruta_archivo, "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    model="whisper-1", 
                    file=audio_file,
                    language="es"
                )
            
            texto_final = transcription.text
            transcripciones_totales.append(f"--- {archivo.filename} ---\n{texto_final}")
            
            # Análisis de texto
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

    # Cálculo de porcentajes
    total_menciones = sum(conteo_acumulado.values())
    porcentajes = {cat: (round((val / total_menciones) * 100, 2) if total_menciones > 0 else 0) 
                for cat, val in conteo_acumulado.items()}

    return jsonify({
        "transcripciones": "\n\n".join(transcripciones_totales),
        "porcentajes": porcentajes
    })

if __name__ == '__main__':
    app.run(debug=True)