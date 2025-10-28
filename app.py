import pandas as pd
from flask import Flask, render_template, request, jsonify, session, send_from_directory
from datetime import timedelta
import io
import openpyxl
import logging
import requests
import os
import base64 # Adicionado para corrigir o erro 'name 'base64' is not defined'
from flask_session import Session  # Adicionado para sessões do lado do servidor

# Configurar o logger
logging.basicConfig(filename='app_debug.log', level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
app.secret_key = 'super_secret_key'

# Configurações de sessão do lado do servidor
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = os.path.join(os.getcwd(), 'flask_session')
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

Session(app)  # Inicializar sessões do lado do servidor

SVG_URL = "https://upload.wikimedia.org/wikipedia/commons/4/4f/Bandeira_do_Esp%C3%ADrito_Santo.svg"
SVG_PATH = "static/bandeira_espirito_santo.svg"

def download_svg(url, path):
    try:
        response = requests.get(url)
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        with open(path, 'wb') as f:
            f.write(response.content)
        logging.info(f"SVG baixado com sucesso para {path}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Erro ao baixar SVG de {url}: {e}")

# Baixar o SVG quando o aplicativo iniciar
with app.app_context():
    if not os.path.exists(SVG_PATH):
        download_svg(SVG_URL, SVG_PATH)

# Função auxiliar para aplicar todos os filtros
def apply_filters():
    logging.debug("Iniciando apply_filters")
    if 'df_original_df' not in session or 'excel_file_content' not in session:
        logging.debug("df_original_df ou excel_file_content não encontrados na sessão.")
        return

    df_original = pd.DataFrame(session['df_original_df'])
    df_filtered = df_original.copy()
    logging.debug(f"DataFrame original carregado para filtragem. Linhas: {len(df_filtered)}")

    # Aplicar filtro de meses
    if 'selected_months' in session and session['selected_months']:
        selected_months = session['selected_months']
        logging.debug(f"Meses selecionados: {selected_months}")
        excel_file_buffer = io.BytesIO(session['excel_file_content'])
        dfs = []
        for month in selected_months:
            # Certifique-se de que o buffer é resetado para cada leitura de aba
            excel_file_buffer.seek(0) 
            df_month = pd.read_excel(excel_file_buffer, sheet_name=month, header=4)
            df_month.columns = df_month.columns.str.strip().str.replace(r'[^\w\s]', '', regex=True)
            df_month['Mês'] = month
            dfs.append(df_month)
        
        if dfs:
            df_months_combined = pd.concat(dfs, ignore_index=True)
            # Filtrar df_filtered para incluir apenas as linhas cujos meses estão em df_months_combined
            df_filtered = df_filtered[df_filtered['Mês'].isin(df_months_combined['Mês'])]
        else:
            df_filtered = pd.DataFrame() # Se nenhum mês válido for encontrado, retorne um DataFrame vazio
        logging.debug(f"Após filtro de meses. Linhas: {len(df_filtered)}")

    # Aplicar filtro de escolas
    if 'selected_schools' in session and session['selected_schools'] and not df_filtered.empty:
        selected_schools = session['selected_schools']
        logging.debug(f"Escolas selecionadas: {selected_schools}")
        df_filtered = df_filtered[df_filtered['ESCOLA'].isin(selected_schools)]
        logging.debug(f"Após filtro de escolas. Linhas: {len(df_filtered)}")

    # Aplicar filtro de colunas
    if 'selected_columns' in session and session['selected_columns'] and not df_filtered.empty:
        selected_columns = session['selected_columns']
        logging.debug(f"Colunas selecionadas: {selected_columns}")
        
        # Garantir que a coluna 'ESCOLA' seja sempre incluída se existir no df original
        final_columns = list(set(selected_columns + ['ESCOLA'])) if 'ESCOLA' in df_original.columns else selected_columns
        
        valid_columns = [col for col in final_columns if col in df_filtered.columns]
        if valid_columns:
            df_filtered = df_filtered[valid_columns]
            logging.debug(f"Após filtro de colunas. Colunas válidas: {valid_columns}")
        else:
            logging.debug("Nenhuma coluna selecionada é válida. Retornando DataFrame vazio.")
            df_filtered = pd.DataFrame()

    session['df_display'] = df_filtered.to_dict(orient='records')
    logging.debug(f"df_display atualizado na sessão. Linhas: {len(session['df_display']) if session['df_display'] else 0}")
    logging.debug("Finalizando apply_filters")


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/set_test_session')
def set_test_session():
    session['test_key'] = 'test_value'
    logging.debug(f"Sessão de teste definida: {session.get('test_key')}")
    return "Sessão de teste definida!"

@app.route('/get_test_session')
def get_test_session():
    logging.debug(f"Conteúdo completo da sessão em get_test_session: {list(session.keys())}")
    test_value = session.get('test_key', 'Não encontrado')
    logging.debug(f"Valor de test_key na sessão: {test_value}")
    return f"Valor da sessão de teste: {test_value}"

@app.route('/upload', methods=['POST'])
def upload_file():
    logging.debug("Iniciando upload_file")
    if 'file' not in request.files:
        logging.debug("Nenhum arquivo enviado.")
        return jsonify({'error': 'Nenhum arquivo enviado'}), 400
    file = request.files['file']
    if file.filename == '':
        logging.debug("Nenhum arquivo selecionado.")
        return jsonify({'error': 'Nenhum arquivo selecionado'}), 400
    if file:
        try:
            file_content = file.read()
            session['excel_file_content'] = base64.b64encode(file_content).decode('utf-8')
            excel_file_buffer = io.BytesIO(file_content)

            workbook = openpyxl.load_workbook(excel_file_buffer)
            sheet_names = workbook.sheetnames

            df = pd.read_excel(excel_file_buffer, sheet_name=sheet_names[0], header=4)
            df.columns = df.columns.str.strip().str.replace(r'[^\w\s]', '', regex=True)

            session['df_original_df'] = df.to_dict(orient='records')
            session['available_schools'] = df['ESCOLA'].dropna().unique().tolist() if 'ESCOLA' in df.columns else []
            session['selected_schools'] = []
            session['selected_months'] = []
            session['selected_columns'] = []
            session['upload_test_data'] = 'dados_do_upload_persistidos'
            session.permanent = True
            session.modified = True  # Marcar sessão como modificada
            logging.debug(f"Arquivo carregado. Linhas do df_original_df: {len(df)}")
            logging.debug(f"Conteúdo da sessão após upload: {list(session.keys())}")
            logging.debug(f"upload_test_data na sessão após upload: {session.get('upload_test_data')}")

            apply_filters()
            return jsonify({'columns': df.columns.tolist(), 'sheet_names': sheet_names, 'schools': session['available_schools']}), 200
        except Exception as e:
            logging.error(f"Erro durante o upload do arquivo: {e}")
            return jsonify({'error': str(e)}), 500

@app.route('/select_columns', methods=['POST'])
def select_columns():
    logging.debug("Iniciando select_columns")
    logging.debug(f"Conteúdo da sessão em select_columns: {list(session.keys())}")
    if 'df_original_df' not in session:
        logging.debug("df_original_df não encontrado na sessão em select_columns.")
        return jsonify({'error': 'Nenhuma planilha carregada'}), 400

    selected_columns = request.json.get('columns')
    if not selected_columns:
        session['selected_columns'] = [] # Limpa as colunas selecionadas se nada for enviado
        logging.debug("Nenhuma coluna selecionada. Limpando selected_columns.")
    else:
        session['selected_columns'] = selected_columns
        logging.debug(f"Colunas selecionadas: {selected_columns}")

    apply_filters() # Aplica os filtros após a seleção de colunas
    logging.debug(f"Após select_columns, df_display na sessão tem {len(session['df_display']) if session['df_display'] else 0} linhas.")

    return jsonify({'message': 'Colunas selecionadas com sucesso!', 'selected_columns': session['selected_columns']}), 200

@app.route('/select_months', methods=['POST'])
def select_months():
    logging.debug("Iniciando select_months")
    logging.debug(f"Conteúdo da sessão em select_months: {list(session.keys())}")
    if 'excel_file_content' not in session:
        logging.debug("excel_file_content não encontrado na sessão em select_months.")
        return jsonify({'error': 'Nenhuma planilha carregada'}), 400

    selected_months = request.json.get('months')
    if not selected_months:
        session['selected_months'] = [] # Limpa os meses selecionados se nada for enviado
        logging.debug("Nenhum mês selecionado. Limpando selected_months.")
    else:
        session['selected_months'] = selected_months
        logging.debug(f"Meses selecionados: {selected_months}")

    apply_filters() # Aplica os filtros após a seleção de meses
    logging.debug(f"Após select_months, df_display na sessão tem {len(session['df_display']) if session['df_display'] else 0} linhas.")

    return jsonify({'message': 'Meses selecionados com sucesso!', 'selected_months': session['selected_months']}), 200

@app.route('/select_schools', methods=['POST'])
def select_schools():
    logging.debug("Iniciando select_schools")
    logging.debug(f"Conteúdo da sessão em select_schools: {list(session.keys())}")
    logging.debug(f"upload_test_data na sessão em select_schools: {session.get('upload_test_data')}")
    if 'df_original_df' not in session:
        logging.debug("df_original_df não encontrado na sessão em select_schools.")
        return jsonify({'error': 'Nenhuma planilha carregada'}), 400

    selected_schools = request.json.get('schools')
    if not selected_schools:
        session['selected_schools'] = [] # Limpa as escolas selecionadas se nada for enviado
        logging.debug("Nenhuma escola selecionada. Limpando selected_schools.")
    else:
        session['selected_schools'] = selected_schools
        logging.debug(f"Escolas selecionadas: {selected_schools}")

    session.modified = True  # Marcar sessão como modificada
    apply_filters()
    logging.debug(f"Após select_schools, df_display na sessão tem {len(session['df_display']) if session['df_display'] else 0} linhas.")

    return jsonify({'message': 'Escolas selecionadas com sucesso!', 'selected_schools': session['selected_schools']}), 200

@app.route('/display_info', methods=['GET', 'POST'])
def display_info():
    logging.debug("Iniciando display_info")
    logging.debug(f"Conteúdo da sessão em display_info: {list(session.keys())}")
    logging.debug(f"upload_test_data na sessão em display_info: {session.get('upload_test_data')}")
    if 'df_display' not in session or not session['df_display']:
        logging.debug("df_display não encontrado ou vazio na sessão.")
        return jsonify({'error': 'Nenhum dado para exibir. Por favor, carregue uma planilha primeiro.'}), 400

    df_display = pd.DataFrame(session['df_display'])
    logging.debug(f"df_display carregado para exibição. Linhas: {len(df_display)}")

    # A filtragem de colunas já é feita em apply_filters, então aqui apenas exibimos
    # o DataFrame já filtrado.

    # Retorna apenas as 5 primeiras linhas para exibição
    logging.debug("Retornando as 5 primeiras linhas para exibição.")
    return jsonify({'info': df_display.head(5).to_dict(orient='records')})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')