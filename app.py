import streamlit as st
from supabase import create_client, Client
import random
import time
import io
import uuid
from PIL import Image, ImageDraw, ImageFont
import pandas as pd
from datetime import datetime
import os

# --- Configuração Inicial ---
st.set_page_config(
    page_title="Number Assignment & Form System",
    layout="centered",
    initial_sidebar_state="expanded"
)

# --- Estilização CSS ---
st.markdown("""
<style>
    .main-header {text-align: center; margin-bottom: 30px;}
    .number-display {font-size: 72px; text-align: center; margin: 30px 0;}
    .success-msg {background-color: #d4edda; color: #155724; padding: 10px; border-radius: 5px;}
    .error-msg {background-color: #f8d7da; color: #721c24; padding: 10px; border-radius: 5px;}
    .sub-header {font-size: 1.5em; color: #2196F3;}
</style>
""", unsafe_allow_html=True)

# --- Funções ---

def get_supabase_client() -> Client:
    """Estabelece conexão com o Supabase usando variáveis de ambiente."""
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        st.error("Credenciais do Supabase não configuradas no ambiente.")
        return None
    try:
        client = create_client(supabase_url, supabase_key)
        client.table("_dummy").select("*").limit(1).execute()
        return client
    except Exception as e:
        st.error(f"Erro ao conectar ao Supabase: {str(e)}")
        return None

def check_table_exists(supabase, table_name):
    """Verifica se uma tabela específica existe no Supabase."""
    try:
        supabase.table(table_name).select("*").limit(1).execute()
        return True
    except Exception:
        return False

def create_meeting_table(supabase, table_name, meeting_name, max_number=999, selected_forms=None):
    """Cria uma nova tabela para uma reunião no Supabase e registra metadados."""
    try:
        response_metadata = supabase.table("meetings_metadata").insert({
            "table_name": table_name,
            "meeting_name": meeting_name,
            "created_at": datetime.now().isoformat(),
            "max_number": max_number
        }).execute()
        meeting_id = response_metadata.data[0]["id"]

        create_table_query = f"""
        CREATE TABLE public.{table_name} (
            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            number INTEGER NOT NULL,
            assigned BOOLEAN DEFAULT FALSE,
            assigned_at TIMESTAMPTZ,
            user_id TEXT
        );
        """
        supabase.rpc("execute_sql", {"query": create_table_query}).execute()

        time.sleep(1)
        if not check_table_exists(supabase, table_name):
            raise Exception(f"Tabela {table_name} não foi criada com sucesso no Supabase.")

        batch_size = 100
        for i in range(0, max_number, batch_size):
            end = min(i + batch_size, max_number)
            data = [{"number": j, "assigned": False, "assigned_at": None, "user_id": None} 
                    for j in range(i+1, end+1)]
            supabase.table(table_name).insert(data).execute()

        if selected_forms:
            for form_id in selected_forms:
                supabase.table("meeting_forms").insert({
                    "meeting_id": meeting_id,
                    "form_id": form_id
                }).execute()
        
        return True
    except Exception as e:
        st.error(f"Erro ao criar tabela de reunião: {str(e)}")
        try:
            supabase.table("meetings_metadata").delete().eq("table_name", table_name).execute()
            supabase.rpc("execute_sql", {"query": f"DROP TABLE IF EXISTS public.{table_name}"}).execute()
        except Exception as rollback_e:
            st.error(f"Erro no rollback: {str(rollback_e)}")
        return False

def get_available_meetings(supabase):
    """Recupera a lista de reuniões disponíveis da tabela de metadados."""
    try:
        response = supabase.table("meetings_metadata").select("*").execute()
        return response.data if response.data else []
    except Exception as e:
        st.error(f"Erro ao recuperar reuniões: {str(e)}")
        return []

def get_available_forms(supabase):
    """Recupera a lista de formulários disponíveis da tabela de metadados."""
    try:
        response = supabase.table("forms_metadata").select("*").execute()
        return response.data if response.data else []
    except Exception as e:
        st.error(f"Erro ao recuperar formulários: {str(e)}")
        return []

def get_forms_for_meeting(supabase, meeting_id):
    """Recupera os formulários associados a uma reunião específica."""
    try:
        response = supabase.table("meeting_forms").select("form_id").eq("meeting_id", meeting_id).execute()
        form_ids = [row["form_id"] for row in response.data]
        if form_ids:
            forms = supabase.table("forms_metadata").select("*").in_("id", form_ids).execute()
            return forms.data if forms.data else []
        return []
    except Exception as e:
        st.error(f"Erro ao recuperar formulários da reunião: {str(e)}")
        return []

def get_answered_forms(supabase, participant_id):
    """Recupera os IDs dos formulários já respondidos por um participant_id."""
    try:
        response = supabase.table("responses").select("form_id").eq("participant_id", participant_id).execute()
        return set(row["form_id"] for row in response.data) if response.data else set()
    except Exception as e:
        st.error(f"Erro ao verificar formulários respondidos: {str(e)}")
        return set()

def generate_number_image(number):
    """Gera uma imagem com o número atribuído."""
    width, height = 600, 300
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    for y in range(height):
        r = int(220 - y/3)
        g = int(240 - y/3)
        b = 255
        for x in range(width):
            draw.point((x, y), fill=(r, g, b))
    
    try:
        font = ImageFont.truetype("Arial.ttf", 200)
    except IOError:
        font = ImageFont.load_default()
    
    number_text = str(number)
    bbox = draw.textbbox((0, 0), number_text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    text_position = ((width - text_width) // 2, (height - text_height) // 2)
    draw.text(text_position, number_text, font=font, fill=(0, 0, 100))
    
    img_buffer = io.BytesIO()
    img.save(img_buffer, format="PNG")
    img_buffer.seek(0)
    return img_buffer

def generate_participant_link(table_name, user_id=None, mode="participant"):
    """Gera um link para participantes acessarem a reunião ou formulário."""
    base_url = "https://mynumber.streamlit.app"
    if user_id:
        return f"{base_url}/?table={table_name}&mode={mode}&user_id={user_id}"
    return f"{base_url}/?table={table_name}&mode={mode}"

# --- Verifica Modo ---
query_params = st.query_params
mode = query_params.get("mode", "master")
table_name_from_url = query_params.get("table", None)

if "user_id" not in st.session_state:
    user_id_from_url = query_params.get("user_id", None)
    if user_id_from_url:
        st.session_state["user_id"] = user_id_from_url
    else:
        st.session_state["user_id"] = str(uuid.uuid4())

if mode == "participant" and table_name_from_url:
    # --- Modo Participante para Reuniões ---
    st.markdown("<h1 class='main-header'>Obtenha Seu Número</h1>", unsafe_allow_html=True)
    supabase = get_supabase_client()
    if not supabase:
        st.stop()
    
    if not check_table_exists(supabase, table_name_from_url):
        st.error("Reunião não encontrada ou inválida.")
        st.stop()
    
    try:
        meeting_info = supabase.table("meetings_metadata").select("*").eq("table_name", table_name_from_url).execute()
        meeting_name = meeting_info.data[0]["meeting_name"] if meeting_info.data else "Reunião"
        meeting_id = meeting_info.data[0]["id"]
        st.subheader(f"Reunião: {meeting_name}")
    except Exception:
        st.subheader("Obtenha um número para a reunião")
        st.stop()

    user_id = st.session_state["user_id"]
    
    participant_link = generate_participant_link(table_name_from_url, user_id, mode="participant")
    st.markdown(f"**Seu Link Persistente para Reunião:** [{participant_link}]({participant_link})")
    st.write("Guarde este link para acessar sempre o mesmo número!")

    try:
        existing = supabase.table(table_name_from_url).select("number").eq("user_id", user_id).execute()
        if existing.data:
            st.session_state["assigned_number"] = existing.data[0]["number"]
        else:
            with st.spinner("Atribuindo um número..."):
                response = supabase.table(table_name_from_url).select("*").eq("assigned", False).execute()
                if response.data:
                    available_numbers = [row["number"] for row in response.data]
                    if available_numbers:
                        assigned_number = random.choice(available_numbers)
                        supabase.table(table_name_from_url).update({
                            "assigned": True,
                            "assigned_at": datetime.now().isoformat(),
                            "user_id": user_id
                        }).eq("number", assigned_number).execute()
                        st.session_state["assigned_number"] = assigned_number
                    else:
                        st.error("Todos os números foram atribuídos!")
                        st.stop()
                else:
                    st.error("Todos os números foram atribuídos!")
                    st.stop()

        st.markdown(f"""
        <div class='success-msg'>
            <p>Seu número atribuído é:</p>
            <div class='number-display'>{st.session_state['assigned_number']}</div>
        </div>
        """, unsafe_allow_html=True)

        st.subheader("Formulários Disponíveis para Você")
        forms = get_forms_for_meeting(supabase, meeting_id)
        participant_id = str(st.session_state["assigned_number"])
        answered_forms = get_answered_forms(supabase, participant_id)
        if forms:
            for form in forms:
                form_id = form["id"]
                form_link = generate_participant_link(form["table_name"], user_id, mode="participant_form")
                status = "✅ Respondido" if form_id in answered_forms else "⏳ Pendente"
                st.markdown(f"- **{form['form_name']}** ({status}): [{form_link}]({form_link})")
        else:
            st.info("Nenhum formulário disponível para esta reunião.")

    except Exception as e:
        st.error(f"Erro ao atribuir número: {str(e)}")
        st.stop()
    
    if st.button("Salvar como Imagem"):
        with st.spinner("Gerando imagem..."):
            img_buffer = generate_number_image(st.session_state["assigned_number"])
            st.image(img_buffer)
            st.download_button(
                "Baixar Imagem",
                img_buffer,
                file_name=f"meu_numero_{st.session_state['assigned_number']}.png",
                mime="image/png"
            )

elif mode == "participant_form" and table_name_from_url:
    # --- Modo Participante para Formulários ---
    st.markdown("<h1 class='main-header'>Responder Formulário</h1>", unsafe_allow_html=True)
    supabase = get_supabase_client()
    if not supabase:
        st.stop()
    
    form_info = supabase.table("forms_metadata").select("*").eq("table_name", table_name_from_url).execute()
    if not form_info.data:
        st.error("Formulário não encontrado.")
        st.stop()

    form_id = form_info.data[0]['id']
    st.subheader(f"Formulário: {form_info.data[0]['form_name']}")

    questions = supabase.table("questions").select("*").eq("form_id", form_id).execute()
    if not questions.data:
        st.error("Nenhuma pergunta encontrada para este formulário.")
        st.stop()

    user_id = st.session_state["user_id"]
    participant_id_default = ""
    meeting_table_name = ""
    for meeting in get_available_meetings(supabase):
        assigned = supabase.table(meeting["table_name"]).select("number").eq("user_id", user_id).execute()
        if assigned.data:
            participant_id_default = str(assigned.data[0]["number"])
            meeting_table_name = meeting["table_name"]
            break
    
    if not participant_id_default:
        st.error("Você precisa ter um número atribuído para responder formulários.")
        st.stop()

    participant_id = participant_id_default
    answered_forms = get_answered_forms(supabase, participant_id)
    if form_id in answered_forms:
        st.warning("Você já respondeu este formulário. Cada participante só pode responder uma vez.")
        st.stop()

    with st.form("form_submission"):
        responses = {}
        for q in questions.data:
            st.write(f"{q['question_text']}")
            if q['question_type'] == 'text':
                responses[q['id']] = st.text_input("Sua resposta", key=f"resp_{q['id']}")
            elif q['question_type'] == 'multiple_choice':
                options = supabase.table("options").select("*").eq("question_id", q['id']).execute()
                option_texts = [opt['option_text'] for opt in options.data]
                option_ids = [opt['id'] for opt in options.data]
                selected_option = st.radio("Escolha uma opção", option_texts, index=None, key=f"resp_{q['id']}")
                if selected_option is not None:
                    responses[q['id']] = option_ids[option_texts.index(selected_option)]
                else:
                    responses[q['id']] = None

        st.text_input("Seu Nome ou ID", value=participant_id, key="participant_id", disabled=True)
        if st.form_submit_button("Enviar"):
            if all(responses.values()):
                for q_id, answer in responses.items():
                    response_data = {
                        "form_id": form_id,
                        "participant_id": participant_id,
                        "question_id": q_id,
                        "answer": str(answer)
                    }
                    supabase.table("responses").insert(response_data).execute()
                st.success("Respostas enviadas com sucesso!")
                st.markdown(f"Voltando para sua página de participante em 3 segundos...")
                time.sleep(3)
                st.query_params.update({
                    "table": meeting_table_name,
                    "mode": "participant",
                    "user_id": user_id
                })
                st.rerun()
            else:
                st.warning("Preencha todas as respostas.")

else:
    # --- Modo Master ---
    valid_pages = ["Gerenciar Reuniões", "Compartilhar Link da Reunião", "Ver Estatísticas", "Gerenciar Formulários", "Compartilhar Link do Formulário"]
    if "page" not in st.session_state or st.session_state["page"] not in valid_pages:
        st.session_state["page"] = "Gerenciar Reuniões"

    st.sidebar.title("Menu (Master)")
    page = st.sidebar.radio("Escolha uma opção", valid_pages, index=valid_pages.index(st.session_state["page"]))

    if page == "Gerenciar Reuniões":
        st.session_state["page"] = "Gerenciar Reuniões"
        st.markdown("<h1 class='main-header'>Gerenciar Reuniões</h1>", unsafe_allow_html=True)
        supabase = get_supabase_client()
        if not supabase:
            st.stop()
        
        with st.form("create_meeting_form"):
            st.subheader("Criar Nova Reunião")
            meeting_name = st.text_input("Nome da Reunião")
            max_number = st.number_input("Número Máximo", min_value=10, max_value=10000, value=999)
            
            forms = get_available_forms(supabase)
            form_options = {f"{f['form_name']} ({f['table_name']})": f["id"] for f in forms}
            selected_forms = st.multiselect("Formulários Disponíveis nesta Reunião", list(form_options.keys()))
            selected_form_ids = [form_options[form] for form in selected_forms] if selected_forms else None

            submit_button = st.form_submit_button("Criar Reunião")
            
            if submit_button:
                if meeting_name:
                    table_name = f"meeting_{int(time.time())}_{meeting_name.lower().replace(' ', '_')}"
                    if check_table_exists(supabase, table_name):
                        st.error("Uma reunião com esse nome já existe. Tente outro nome.")
                    else:
                        with st.spinner("Criando reunião..."):
                            success = create_meeting_table(supabase, table_name, meeting_name, max_number, selected_form_ids)
                            if success:
                                participant_link = generate_participant_link(table_name, mode="participant")
                                st.success(f"Reunião '{meeting_name}' criada com sucesso!")
                                st.markdown(f"**Link para Participantes:** [{participant_link}]({participant_link})")
                                st.session_state["selected_table"] = table_name
                                st.session_state["page"] = "Compartilhar Link da Reunião"
                                st.rerun()
                            else:
                                st.error("Falha ao criar a reunião.")
                else:
                    st.warning("Por favor, insira um nome para a reunião.")
        
        st.subheader("Reuniões Existentes")
        meetings = get_available_meetings(supabase)
        if meetings:
            meeting_data = []
            for meeting in meetings:
                if "table_name" in meeting and "meeting_name" in meeting:
                    table_name = meeting["table_name"]
                    if check_table_exists(supabase, table_name):
                        try:
                            count_response = supabase.table(table_name).select("*", count="exact").eq("assigned", True).execute()
                            assigned_count = count_response.count if hasattr(count_response, 'count') else 0
                            participant_link = generate_participant_link(table_name, mode="participant")
                            meeting_data.append({
                                "Nome": meeting.get("meeting_name", "Sem nome"),
                                "Tabela": table_name,
                                "Link": participant_link,
                                "Criada em": meeting.get("created_at", "")[:16].replace("T", " "),
                                "Números Atribuídos": assigned_count,
                                "Total de Números": meeting.get("max_number", 0)
                            })
                        except Exception as e:
                            st.warning(f"Erro ao processar reunião {table_name}: {str(e)}")
            if meeting_data:
                df = pd.DataFrame(meeting_data)
                st.dataframe(df)
            else:
                st.info("Nenhuma reunião válida encontrada.")
        else:
            st.info("Nenhuma reunião disponível ou erro ao acessar o Supabase.")

    elif page == "Compartilhar Link da Reunião":
        st.session_state["page"] = "Compartilhar Link da Reunião"
        st.markdown("<h1 class='main-header'>Compartilhar Link da Reunião</h1>", unsafe_allow_html=True)
        
        supabase = get_supabase_client()
        if not supabase:
            st.stop()
        
        meetings = get_available_meetings(supabase)
        if not meetings:
            st.info("Nenhuma reunião disponível. Crie uma reunião primeiro.")
            st.stop()
        
        options = {f"{m['meeting_name']} ({m['table_name']})": m["table_name"] 
                   for m in meetings if "table_name" in m and "meeting_name" in m}
        selected = st.selectbox("Selecione uma reunião para compartilhar:", list(options.keys()))
        
        if selected:
            selected_table = options[selected]
            participant_link = generate_participant_link(selected_table, mode="participant")
            st.markdown(f"**Link para Participantes:** [{participant_link}]({participant_link})")
            if st.button("Copiar Link"):
                st.write("Link copiado para a área de transferência!")
                st.code(participant_link)

    elif page == "Ver Estatísticas":
        st.session_state["page"] = "Ver Estatísticas"
        st.markdown("<h1 class='main-header'>Estatísticas da Reunião</h1>", unsafe_allow_html=True)
        supabase = get_supabase_client()
        if not supabase:
            st.stop()
        
        meetings = get_available_meetings(supabase)
        if not meetings:
            st.info("Nenhuma reunião disponível para análise.")
            st.stop()
        
        options = {f"{m['meeting_name']} ({m['table_name']})": m["table_name"] 
                   for m in meetings if "table_name" in m and "meeting_name" in m}
        selected = st.selectbox("Selecione uma reunião:", list(options.keys()))
        
        if selected:
            selected_table = options[selected]
            meeting_info = supabase.table("meetings_metadata").select("id").eq("table_name", selected_table).execute()
            meeting_id = meeting_info.data[0]["id"]
            
            try:
                total_response = supabase.table(selected_table).select("*", count="exact").execute()
                total_numbers = total_response.count if hasattr(total_response, 'count') else 0
                assigned_response = supabase.table(selected_table).select("*", count="exact").eq("assigned", True).execute()
                assigned_numbers = assigned_response.count if hasattr(assigned_response, 'count') else 0
                percentage = (assigned_numbers / total_numbers) * 100 if total_numbers > 0 else 0
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total de Números", total_numbers)
                with col2:
                    st.metric("Números Atribuídos", assigned_numbers)
                with col3:
                    st.metric("Porcentagem Atribuída", f"{percentage:.1f}%")
                
                try:
                    time_data_response = supabase.table(selected_table).select("*").eq("assigned", True).order("assigned_at").execute()
                    if time_data_response.data:
                        time_data = []
                        for item in time_data_response.data:
                            if item.get("assigned_at"):
                                time_data.append({
                                    "time": item.get("assigned_at")[:16].replace("T", " "),
                                    "count": 1
                                })
                        if time_data:
                            df = pd.DataFrame(time_data)
                            df["time"] = pd.to_datetime(df["time"])
                            df["hour"] = df["time"].dt.floor("H")
                            hourly_counts = df.groupby("hour").count().reset_index()
                            hourly_counts["hour_str"] = hourly_counts["hour"].dt.strftime("%m/%d %H:00")
                            st.subheader("Atribuições de Números por Hora")
                            st.bar_chart(data=hourly_counts, x="hour_str", y="count")
                except Exception:
                    st.info("Dados temporais não disponíveis para esta reunião.")
                
                if st.button("Exportar Dados de Números"):
                    try:
                        all_data_response = supabase.table(selected_table).select("*").execute()
                        if all_data_response.data:
                            df = pd.DataFrame(all_data_response.data)
                            csv = df.to_csv(index=False)
                            st.download_button(
                                "Baixar CSV",
                                csv,
                                file_name=f"{selected_table}_numeros_export.csv",
                                mime="text/csv"
                            )
                    except Exception as e:
                        st.error(f"Erro ao exportar dados: {str(e)}")
            except Exception as e:
                st.error(f"Erro ao recuperar estatísticas de números: {str(e)}")

            st.subheader("Respostas dos Formulários")
            forms = get_forms_for_meeting(supabase, meeting_id)
            if forms:
                form_ids = [f["id"] for f in forms]
                responses = supabase.table("responses").select("participant_id, form_id, question_id, answer").in_("form_id", form_ids).execute()
                if responses.data:
                    response_data = []
                    for resp in responses.data:
                        form = next((f for f in forms if f["id"] == resp["form_id"]), None)
                        question = supabase.table("questions").select("question_text, question_type, correct_answer").eq("id", resp["question_id"]).execute().data[0]
                        
                        answer_display = resp["answer"]
                        is_correct = None
                        if question["question_type"] == "multiple_choice":
                            option = supabase.table("options").select("option_text").eq("id", resp["answer"]).execute()
                            answer_display = option.data[0]["option_text"] if option.data else resp["answer"]
                            if question["correct_answer"]:
                                is_correct = "✅ Correta" if resp["answer"] == question["correct_answer"] else "❌ Incorreta"
                        elif question["question_type"] == "text" and question["correct_answer"]:
                            is_correct = "✅ Correta" if resp["answer"].lower() == question["correct_answer"].lower() else "❌ Incorreta"

                        response_data.append({
                            "Participante": resp["participant_id"],
                            "Formulário": form["form_name"] if form else "Desconhecido",
                            "Pergunta": question["question_text"],
                            "Resposta": answer_display,
                            "Correta": is_correct if is_correct is not None else "N/A"
                        })
                    
                    df = pd.DataFrame(response_data)
                    st.dataframe(df)
                    
                    if st.button("Exportar Respostas dos Formulários"):
                        csv = df.to_csv(index=False)
                        st.download_button(
                            "Baixar CSV",
                            csv,
                            file_name=f"{selected_table}_respostas_export.csv",
                            mime="text/csv"
                        )
                else:
                    st.info("Nenhuma resposta registrada para os formulários desta reunião.")
            else:
                st.info("Nenhum formulário associado a esta reunião.")

    elif page == "Gerenciar Formulários":
        st.session_state["page"] = "Gerenciar Formulários"
        st.markdown("<h1 class='main-header'>Gerenciar Formulários</h1>", unsafe_allow_html=True)
        supabase = get_supabase_client()
        if not supabase:
            st.stop()
        
        with st.form("create_form_form"):
            st.subheader("Criar Novo Formulário")
            form_name = st.text_input("Nome do Formulário", key="form_name")

            if 'questions' not in st.session_state:
                st.session_state['questions'] = []
            if 'current_options' not in st.session_state:
                st.session_state['current_options'] = []
            if 'show_options_form' not in st.session_state:
                st.session_state['show_options_form'] = False
            if 'current_question_index' not in st.session_state:
                st.session_state['current_question_index'] = None
            if 'question_text' not in st.session_state:
                st.session_state['question_text'] = ""
            if 'option_text' not in st.session_state:
                st.session_state['option_text'] = ""
            if 'delete_trigger' not in st.session_state:
                st.session_state['delete_trigger'] = None

            st.markdown("<h3 class='sub-header'>Adicionar Pergunta</h3>", unsafe_allow_html=True)
            question_type = st.selectbox("Tipo da Pergunta", ["Texto", "Múltipla Escolha"], key="q_type")
            question_text = st.text_input("Texto da Pergunta", value=st.session_state['question_text'], placeholder="Digite o texto da pergunta", key="q_text")

            if st.form_submit_button("Adicionar Pergunta"):
                if question_text:
                    question_data = {
                        'type': 'text' if question_type == "Texto" else 'multiple_choice',
                        'text': question_text,
                        'options': [],
                        'correct': None
                    }
                    st.session_state['questions'].append(question_data)
                    if question_type == "Múltipla Escolha":
                        st.session_state['show_options_form'] = True
                        st.session_state['current_question_index'] = len(st.session_state['questions']) - 1
                        st.session_state['current_options'] = []
                    else:
                        st.session_state['show_options_form'] = False
                    st.session_state['question_text'] = ""
                    st.success(f"Pergunta '{question_text}' adicionada!")
                else:
                    st.warning("O texto da pergunta é obrigatório.")

            if st.session_state['show_options_form'] and st.session_state['current_question_index'] is not None:
                st.markdown("<h3 class='sub-header'>Adicionar Opções</h3>", unsafe_allow_html=True)
                option_text = st.text_input("Texto da Opção", value=st.session_state['option_text'], placeholder="Digite o texto da opção", key="opt_text")
                if st.form_submit_button("Adicionar Opção"):
                    if option_text:
                        st.session_state['current_options'].append(option_text)
                        st.session_state['option_text'] = ""
                        st.success(f"Opção '{option_text}' adicionada!")
                    else:
                        st.warning("O texto da opção é obrigatório.")

                if st.session_state['current_options']:
                    st.write("Opções adicionadas até agora:")
                    for i, opt in enumerate(st.session_state['current_options']):
                        st.write(f"{i+1}. {opt}")

                if len(st.session_state['current_options']) >= 2:
                    correct_option = st.selectbox("Opção Correta (opcional)", ["Nenhuma"] + st.session_state['current_options'], key="correct_opt")
                    if st.form_submit_button("Finalizar Opções"):
                        current_idx = st.session_state['current_question_index']
                        st.session_state['questions'][current_idx]['options'] = st.session_state['current_options']
                        if correct_option != "Nenhuma":
                            st.session_state['questions'][current_idx]['correct'] = correct_option
                        st.session_state['show_options_form'] = False
                        st.session_state['current_question_index'] = None
                        st.session_state['current_options'] = []
                        st.session_state['option_text'] = ""
                        st.success("Opções e resposta correta (se selecionada) salvas!")

            if st.session_state['questions']:
                st.markdown("<h3 class='sub-header'>Perguntas Adicionadas</h3>", unsafe_allow_html=True)
                for i, q in enumerate(st.session_state['questions'][:]):
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        st.write(f"{i+1}. {q['text']} ({q['type']})")
                        if q['type'] == 'multiple_choice' and q['options']:
                            st.write("Opções:", ", ".join(q['options']))
                            st.write(f"Correta: {q['correct'] if q['correct'] else 'Nenhuma'}")
                        elif q['type'] == 'text':
                            st.write(f"Correta: {q['correct'] if q['correct'] else 'Nenhuma'}")
                    with col2:
                        if st.button("Deletar", key=f"del_{i}_{uuid.uuid4()}"):
                            st.session_state['delete_trigger'] = i

                if st.session_state['delete_trigger'] is not None:
                    i = st.session_state['delete_trigger']
                    st.session_state['questions'].pop(i)
                    if st.session_state['current_question_index'] == i:
                        st.session_state['show_options_form'] = False
                        st.session_state['current_question_index'] = None
                        st.session_state['current_options'] = []
                    elif st.session_state['current_question_index'] is not None and st.session_state['current_question_index'] > i:
                        st.session_state['current_question_index'] -= 1
                    st.success(f"Pergunta {i+1} deletada!")
                    st.session_state['delete_trigger'] = None

            if st.form_submit_button("Criar Formulário"):
                if form_name and st.session_state['questions']:
                    table_name = f"form_{int(time.time())}_{form_name.lower().replace(' ', '_')}"
                    form_data = {"form_name": form_name, "table_name": table_name, "created_at": datetime.now().isoformat()}
                    form_response = supabase.table("forms_metadata").insert(form_data).execute()
                    form_id = form_response.data[0]['id']

                    for q in st.session_state['questions']:
                        question_data = {
                            "form_id": form_id,
                            "question_text": q['text'],
                            "question_type": q['type'],
                            "correct_answer": q['correct']
                        }
                        q_response = supabase.table("questions").insert(question_data).execute()
                        question_id = q_response.data[0]['id']

                        if q['type'] == 'multiple_choice' and q['options']:
                            for opt in q['options']:
                                opt_data = {"question_id": question_id, "option_text": opt}
                                opt_response = supabase.table("options").insert(opt_data).execute()
                                if opt == q['correct']:
                                    supabase.table("questions").update({"correct_answer": str(opt_response.data[0]['id'])}).eq("id", question_id).execute()

                    participant_link = generate_participant_link(table_name, mode="participant_form")
                    st.success(f"Formulário '{form_name}' criado com sucesso!")
                    st.markdown(f"**Link Geral para Participantes:** [{participant_link}]({participant_link})")
                    st.session_state['questions'] = []
                    st.session_state['show_options_form'] = False
                    st.session_state['current_question_index'] = None
                    st.session_state['current_options'] = []
                    st.session_state['question_text'] = ""
                    st.session_state['option_text'] = ""
                    st.session_state["selected_form_table"] = table_name
                    st.session_state["page"] = "Compartilhar Link do Formulário"
                    st.rerun()
                else:
                    st.warning("Insira um nome para o formulário e pelo menos uma pergunta.")

        st.subheader("Formulários Disponíveis")
        forms = get_available_forms(supabase)
        if forms:
            form_data = []
            for form in forms:
                participant_link = generate_participant_link(form["table_name"], mode="participant_form")
                form_data.append({
                    "Nome": form["form_name"],
                    "Link Geral": participant_link,
                    "Criado em": form["created_at"][:16].replace("T", " ")
                })
            df = pd.DataFrame(form_data)
            st.dataframe(df, column_config={"Link Geral": st.column_config.LinkColumn("Link Geral")})
        else:
            st.info("Nenhum formulário disponível.")

    elif page == "Compartilhar Link do Formulário":
        st.session_state["page"] = "Compartilhar Link do Formulário"
        st.markdown("<h1 class='main-header'>Compartilhar Link do Formulário</h1>", unsafe_allow_html=True)
        
        supabase = get_supabase_client()
        if not supabase:
            st.stop()
        
        forms = get_available_forms(supabase)
        if not forms:
            st.info("Nenhum formulário disponível. Crie um formulário primeiro.")
            st.stop()
        
        options = {f"{f['form_name']} ({f['table_name']})": f["table_name"] 
                   for f in forms if "table_name" in f and "form_name" in f}
        selected = st.selectbox("Selecione um formulário para compartilhar:", list(options.keys()))
        
        if selected:
            selected_table = options[selected]
            participant_link = generate_participant_link(selected_table, mode="participant_form")
            st.markdown(f"**Link Geral para Participantes:** [{participant_link}]({participant_link})")
            if st.button("Copiar Link Geral"):
                st.write("Link copiado para a área de transferência!")
                st.code(participant_link)

            st.subheader("Links Únicos por Usuário")
            meetings = get_available_meetings(supabase)
            user_links = []
            for meeting in meetings:
                assigned_users = supabase.table(meeting["table_name"]).select("user_id, number").eq("assigned", True).execute()
                for user in assigned_users.data:
                    user_link = generate_participant_link(selected_table, user["user_id"], mode="participant_form")
                    user_links.append({"Número": user["number"], "Link": user_link})
            if user_links:
                df = pd.DataFrame(user_links)
                st.dataframe(df, column_config={"Link": st.column_config.LinkColumn("Link")})
            else:
                st.info("Nenhum usuário com número atribuído encontrado.")

if __name__ == "__main__":
    pass
