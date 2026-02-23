import os
import re
import uuid
import io
from flask import Flask, render_template, request, jsonify, send_file
from openai import OpenAI
import pandas as pd
from docx import Document
from docx.shared import Pt

app = Flask(__name__)

# Configuración del cliente Groq
client = OpenAI(
    api_key=os.environ.get("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Memoria temporal para guardar el último resultado y poder descargarlo
# (En un sistema real con usuarios, usaríamos una base de datos o redis)
RESULTS_CACHE = {}

MARKET_KEYWORDS = {
    "Precio/Costos": ["precio", "costo", "caro", "barato", "oferta", "pago", "dinero", "soles", "dólares", "inversión"],
    "Calidad/Producto": ["calidad", "bueno", "malo", "excelente", "falla", "material", "duradero", "acabado"],
    "Servicio/Atención": ["atención", "servicio", "soporte", "ayuda", "rápido", "lento", "amable", "queja"],
    "Cantidad/Ventas": ["cantidad", "vendido", "unidades", "stock", "total", "volumen", "pedido"]
}

def generar_resumen_ia(texto):
    if not texto.strip():
        return "No hay texto suficiente para generar un resumen."
    
    prompt = f"""
    Actúa como un consultor de negocios senior. Analiza la siguiente transcripción de audios de un estudio de mercado.
    
    Tu tarea es generar un RESUMEN EJECUTIVO PROFESIONAL.
    1.  **Extrae Datos Duros:** Identifica y lista cualquier cifra mencionada: precios específicos (ej. "$50"), cantidades (ej. "100 unidades"), costos, etc.
    2.  **Identifica Tendencias:** Resume los puntos de dolor principales y las opiniones positivas más repetidas.
    3.  **Formato:** Usa un lenguaje formal de negocios. Utiliza viñetas claras y subtítulos en negrita para organizar la información.

    Transcripción:
    {texto}
    """
    
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2 # Temperatura baja para ser más preciso y menos creativo
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error al generar resumen ejecutivo: {str(e)}"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analizar', methods=['POST'])
def analizar_multiples():
    archivos = request.files.getlist('audios')
    if not archivos or archivos[0].filename == '':
        return jsonify({"error": "No seleccionaste archivos"}), 400
    
    transcripciones_list = []
    conteo_acumulado = {cat: 0 for cat in MARKET_KEYWORDS.keys()}

    for archivo in archivos:
        ruta_archivo = os.path.join(UPLOAD_FOLDER, archivo.filename)
        archivo.save(ruta_archivo)
        
        try:
            with open(ruta_archivo, "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    model="whisper-large-v3", 
                    file=audio_file,
                    language="es"
                )
            
            texto_final = transcription.text
            transcripciones_list.append({"archivo": archivo.filename, "texto": texto_final})
            
            texto_limpio = re.sub(r'[^\w\s]', '', texto_final.lower())
            for categoria, sinonimos in MARKET_KEYWORDS.items():
                for palabra in sinonimos:
                    patron = r'\b' + re.escape(palabra) + r'\b'
                    conteo_acumulado[categoria] += len(re.findall(patron, texto_limpio))
        except Exception as e:
             return jsonify({"error": f"Error en {archivo.filename}: {str(e)}"}), 500
        finally:
            if os.path.exists(ruta_archivo):
                os.remove(ruta_archivo)

    texto_unido_para_resumen = "\n\n".join([f"--- {t['archivo']} ---\n{t['texto']}" for t in transcripciones_list])
    resumen_inteligente = generar_resumen_ia(texto_unido_para_resumen)

    total_menciones = sum(conteo_acumulado.values())
    porcentajes = {cat: (round((val / total_menciones) * 100, 1) if total_menciones > 0 else 0) 
                  for cat, val in conteo_acumulado.items()}

    # Generar un ID único para este análisis
    analysis_id = str(uuid.uuid4())
    
    # Guardar los datos en la caché temporal para poder descargarlos luego
    RESULTS_CACHE[analysis_id] = {
        "resumen": resumen_inteligente,
        "transcripciones": transcripciones_list,
        "conteo": conteo_acumulado,
        "porcentajes": porcentajes,
        "total_menciones": total_menciones
    }

    return jsonify({
        "analysis_id": analysis_id, # Devolvemos el ID al frontend
        "resumen": resumen_inteligente,
        "porcentajes": porcentajes
    })

# --- RUTAS DE DESCARGA ---

@app.route('/download/word/<analysis_id>')
def download_word(analysis_id):
    data = RESULTS_CACHE.get(analysis_id)
    if not data: return "Datos no encontrados o expirados.", 404

    document = Document()
    document.add_heading('Reporte de Análisis de Mercado (IA)', 0)

    document.add_heading('1. Resumen Ejecutivo', level=1)
    document.add_paragraph(data['resumen'])

    document.add_heading('2. Análisis de Tendencias (Frecuencia)', level=1)
    table = document.add_table(rows=1, cols=3)
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = 'Categoría'
    hdr_cells[1].text = 'Menciones'
    hdr_cells[2].text = 'Participación (%)'
    
    for cat, count in data['conteo'].items():
        row_cells = table.add_row().cells
        row_cells[0].text = cat
        row_cells[1].text = str(count)
        row_cells[2].text = f"{data['porcentajes'][cat]}%"

    document.add_heading('3. Transcripciones Detalladas', level=1)
    for item in data['transcripciones']:
        p = document.add_paragraph()
        run = p.add_run(f"Archivo: {item['archivo']}")
        run.bold = True
        document.add_paragraph(item['texto'])
        document.add_paragraph("-" * 20)

    # Guardar en memoria y enviar
    f = io.BytesIO()
    document.save(f)
    f.seek(0)
    return send_file(f, as_attachment=True, download_name=f'Reporte_Mercado_{analysis_id[:8]}.docx')

@app.route('/download/excel/<analysis_id>')
def download_excel(analysis_id):
    data = RESULTS_CACHE.get(analysis_id)
    if not data: return "Datos no encontrados o expirados.", 404

    # Crear DataFrames de Pandas
    df_resumen = pd.DataFrame({"Resumen Ejecutivo": [data['resumen']]})
    
    df_metricas = pd.DataFrame(list(data['conteo'].items()), columns=['Categoría', 'Menciones'])
    df_metricas['Porcentaje'] = df_metricas['Categoría'].map(data['porcentajes'])

    df_transcripciones = pd.DataFrame(data['transcripciones'])

    # Guardar en memoria usando ExcelWriter
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_metricas.to_excel(writer, sheet_name='Métricas', index=False)
        df_resumen.to_excel(writer, sheet_name='Resumen', index=False)
        df_transcripciones.to_excel(writer, sheet_name='Transcripciones', index=False)

    output.seek(0)
    return send_file(output, as_attachment=True, download_name=f'Data_Mercado_{analysis_id[:8]}.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

if __name__ == '__main__':
    app.run(debug=True)