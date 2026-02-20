import os
import re
import whisper
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
model = whisper.load_model("base")

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

MARKET_KEYWORDS = {
    "Precio": ["precio", "costo", "caro", "barato", "oferta", "pago", "dinero"],
    "Calidad": ["calidad", "bueno", "malo", "excelente", "falla", "duración", "material"],
    "Servicio": ["atención", "servicio", "soporte", "ayuda", "rápido", "lento", "amabilidad"],
    "Competencia": ["competencia", "otros", "marca", "diferente", "mejor", "peor"]
}

def analizar_texto(texto):
    texto_limpio = re.sub(r'[^\w\s]', '', texto.lower())
    resultados = {}
    for categoria, sinonimos in MARKET_KEYWORDS.items():
        conteo = 0
        for palabra in sinonimos:
            patron = r'\b' + re.escape(palabra) + r'\b'
            conteo += len(re.findall(patron, texto_limpio))
        resultados[categoria] = conteo
    return resultados

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analizar', methods=['POST'])
def analizar_multiples():
    # Recibir múltiples archivos bajo la misma llave 'audios'
    archivos = request.files.getlist('audios')
    if not archivos or archivos[0].filename == '':
        return jsonify({"error": "No seleccionaste archivos"}), 400
    
    transcripciones_totales = []
    conteo_acumulado = {cat: 0 for cat in MARKET_KEYWORDS.keys()}

    for archivo in archivos:
        ruta_archivo = os.path.join(UPLOAD_FOLDER, archivo.filename)
        archivo.save(ruta_archivo)
        
        try:
            result = model.transcribe(ruta_archivo, language="es")
            texto_final = result['text']
            transcripciones_totales.append(f"--- {archivo.filename} ---\n{texto_final}")
            
            # Analizar y sumar al acumulado
            analisis_archivo = analizar_texto(texto_final)
            for cat in conteo_acumulado:
                conteo_acumulado[cat] += analisis_archivo[cat]
        finally:
            if os.path.exists(ruta_archivo):
                os.remove(ruta_archivo)

    # Calcular porcentajes
    total_menciones = sum(conteo_acumulado.values())
    porcentajes = {}
    if total_menciones > 0:
        porcentajes = {cat: round((val / total_menciones) * 100, 2) for cat, val in conteo_acumulado.items()}
    else:
        porcentajes = {cat: 0 for cat in conteo_acumulado.keys()}

    return jsonify({
        "transcripciones": "\n\n".join(transcripciones_totales),
        "porcentajes": porcentajes
    })

if __name__ == '__main__':
    app.run(debug=True)