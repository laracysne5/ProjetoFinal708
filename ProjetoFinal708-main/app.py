import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from supabase import create_client, Client

# ==========================================
# 1. CONFIGURAÇÕES INICIAIS E AMBIENTE
# ==========================================
load_dotenv()

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("ERRO CRÍTICO: SUPABASE_URL ou SUPABASE_KEY não foram encontradas no arquivo .env")

# Inicializa o cliente do Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__)
app.secret_key = '12345'  # Chave para criptografar as sessões e mensagens (flash)


# ==========================================
# 2. SISTEMA DE LOGIN, LOGOUT E CADASTRO
# ==========================================

# --- ROTA: LOGIN (PÁGINA INICIAL) ---
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        
        try:
            # Busca o usuário comparando o E-mail E a Senha diretamente (Texto Puro)
            resposta = supabase.table('usuarios').select('*').eq('email', email).eq('senha', senha).execute()
            
            if len(resposta.data) > 0:
                usuario = resposta.data[0]
                session['id_usuario'] = usuario['id']
                return redirect(url_for('dashboard'))
            else:
                flash('E-mail ou senha incorretos! Tente novamente.', 'danger')
                print("Login falhou: Credenciais inválidas.")
                
        except Exception as e:
            print(f"Erro de conexão com o Supabase no Login: {e}")
            flash('Erro ao conectar com o banco de dados.', 'danger')
            
    return render_template('index.html')


# --- ROTA: TELA E PROCESSAMENTO DE CADASTRO DE USUÁRIO ---
@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        nome = request.form.get("nome")
        email = request.form.get("email")
        senha_pura = request.form.get("senha")
        
        novo_usuario = {
            "nome": nome,
            "email": email,
            "senha": senha_pura
        }
        
        try:
            supabase.table("usuarios").insert(novo_usuario).execute()
            flash('Usuário cadastrado com sucesso! Faça login.', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            erro_detalhado = str(e)
            print(f"Erro ao cadastrar usuário no Supabase: {erro_detalhado}")
            flash(f'Erro no Banco de Dados: {erro_detalhado}', 'danger')
            
    return render_template('cadastro.html')


# --- ROTA: LOGOUT (SAIR DO SISTEMA) ---
@app.route('/logout')
def logout():
    session.clear()  # Apaga os dados da sessão
    flash('Você saiu do sistema.', 'info')
    return redirect(url_for('index'))


# ==========================================
# 3. PAINEL PRINCIPAL (DASHBOARD GERAL)
# ==========================================

@app.route('/dashboard')
def dashboard():
    if 'id_usuario' not in session:
        flash('Por favor, faça login para acessar o painel.', 'warning')
        return redirect(url_for('index'))
        
    try:
        # 1. Busca dados para contagem de clientes e veículos
        clientes = supabase.table("clientes").select("id, nome, email, telefone, veiculos(id)").execute().data
        
        # 2. Busca peças para contar o total de itens em estoque
        pecas = supabase.table("pecas").select("id, quantidade_estoque").execute().data
        total_pecas = sum(p['quantidade_estoque'] for p in pecas) if pecas else 0
        
        # 3. Busca ordens de serviço para os indicadores e para a tabela do painel
        ordens = supabase.table("ordens_servico").select(
            "id, status, descricao_problema, preco_total, criado_em, clientes(nome), veiculos(modelo, placa)"
        ).order("id", desc=True).execute().data
        
        # 4. Filtra e conta as OS por status
        os_abertas = len([o for o in ordens if o['status'] == 'Aberta']) if ordens else 0
        os_andamento = len([o for o in ordens if o['status'] == 'Em Andamento']) if ordens else 0
        
    except Exception as e:
        print(f"Erro ao carregar dados do Dashboard: {e}")
        clientes = []
        total_pecas = 0
        ordens = []
        os_abertas = 0
        os_andamento = 0
        
    return render_template(
        'dashboard.html', 
        clientes=clientes, 
        total_pecas=total_pecas, 
        ordens=ordens, 
        os_abertas=os_abertas,
        os_andamento=os_andamento
    )


# ==========================================
# 4. MODULO: CLIENTES E VEÍCULOS
# ==========================================

@app.route('/clientes', methods=['GET'])
def listar_clientes():
    if 'id_usuario' not in session:
        return redirect(url_for('index'))

    try:
        # Busca os clientes com seus respectivos veículos para a tabela
        lista_clientes = supabase.table("clientes").select("id, nome, email, telefone, veiculos(marca, modelo, placa)").execute().data 
        
        # BUSCA DE CLIENTES PARA O SELECT DO MODAL "CADASTRAR VEÍCULO"
        lista_selecao_clientes = supabase.table("clientes").select("id, nome").order("nome").execute().data
    except Exception as e:
        print(f"Erro ao buscar lista de clientes: {e}")
        flash('Erro ao carregar a lista de clientes.', 'danger')
        lista_clientes = []
        lista_selecao_clientes = []

    return render_template('clientes.html', clientes=lista_clientes, clientes_select=lista_selecao_clientes)


@app.route('/cadastrar_cliente', methods=['POST'])
def cadastrar_cliente():
    if 'id_usuario' not in session:
        return redirect(url_for('index'))

    novo_cliente = {
        "nome": request.form.get("nome"),
        "email": request.form.get("email"),
        "telefone": request.form.get("telefone")
    }
    try:
        supabase.table("clientes").insert(novo_cliente).execute()
        flash('Cliente cadastrado com sucesso!', 'success')
    except Exception as e:
        print(f"Erro ao cadastrar cliente: {e}")
        flash('Erro ao cadastrar cliente.', 'danger')

    return redirect(url_for('listar_clientes'))


@app.route('/cadastrar_veiculo', methods=['POST'])
def cadastrar_veiculo():
    if 'id_usuario' not in session:
        return redirect(url_for('index'))

    novo_veiculo = {
        "marca": request.form.get("marca"),
        "modelo": request.form.get("modelo"),
        "placa": request.form.get("placa"),
        "cliente_id": int(request.form.get("cliente_id"))  # ID vindo do novo <select> do modal
    }
    try:
        supabase.table("veiculos").insert(novo_veiculo).execute()
        flash('Veículo vinculado com sucesso!', 'success')
    except Exception as e:
        print(f"Erro ao cadastrar veículo: {e}")
        flash('Erro ao cadastrar veículo. Verifique os dados.', 'danger')

    return redirect(url_for('listar_clientes'))


# ==========================================
# 5. MÓDULO: MECÂNICOS
# ==========================================

@app.route('/mecanicos', methods=['GET', 'POST'])
def gerenciar_mecanicos():
    if 'id_usuario' not in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        novo_mecanico = {
            "nome": request.form.get("nome"),
            "especialidade": request.form.get("especialidade"),
            "telefone": request.form.get("telefone")
        }
        try:
            supabase.table("mecânicos").insert(novo_mecanico).execute()
            flash('Mecânico cadastrado com sucesso!', 'success')
        except Exception as e:
            flash(f'Erro ao cadastrar mecânico: {e}', 'danger')
        return redirect(url_for('gerenciar_mecanicos'))

    lista_mecanicos = supabase.table("mecânicos").select("*").order("nome").execute().data
    return render_template('mecanicos.html', mecanicos=lista_mecanicos)


# ==========================================
# 6. MÓDULO: ESTOQUE DE PEÇAS
# ==========================================

@app.route('/estoque', methods=['GET'])
def listar_estoque():
    if 'id_usuario' not in session:
        return redirect(url_for('index'))
        
    lista_pecas = supabase.table("pecas").select("*").order("nome").execute().data
    return render_template('estoque.html', pecas=lista_pecas)


@app.route('/estoque/adicionar', methods=['POST'])
def adicionar_peca():
    if 'id_usuario' not in session:
        return redirect(url_for('index'))

    nova_peca = {
        "nome": request.form.get("nome"),
        "codigo": request.form.get("codigo"),
        "quantidade_estoque": int(request.form.get("quantidade")),
        "preco_venda": float(request.form.get("preco"))
    }
    try:
        supabase.table("pecas").insert(nova_peca).execute()
        flash('Peça adicionada ao estoque com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao adicionar peça: {e}', 'danger')
        
    return redirect(url_for('listar_estoque'))


@app.route('/estoque/editar/<id_peca>', methods=['POST'])
def editar_quantidade(id_peca):
    if 'id_usuario' not in session:
        return redirect(url_for('index'))

    nova_qtd = int(request.form.get("nova_quantidade"))
    try:
        supabase.table("pecas").update({"quantidade_estoque": nova_qtd}).eq("id", id_peca).execute()
        flash('Quantidade updated com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao atualizar estoque: {e}', 'danger')
        
    return redirect(url_for('listar_estoque'))


# ==========================================
# 7. MÓDULO: ORDENS DE SERVIÇO
# ==========================================

@app.route('/os', methods=['GET'])
def listar_ordens():
    if 'id_usuario' not in session:
        return redirect(url_for('index'))
        
    try:
        resposta = supabase.table("ordens_servico").select(
            "id, status, descricao_problema, preco_total, criado_em, clientes(nome), veiculos(marca, modelo, placa), mecânicos(nome)"
        ).order("id", desc=True).execute()
        lista_os = resposta.data
    except Exception as e:
        print(f"Erro ao listar OS: {e}")
        flash('Erro ao carregar a lista de Ordens de Serviço.', 'danger')
        lista_os = []
        
    return render_template('ordens.html', ordens=lista_os)


@app.route('/os/nova', methods=['GET', 'POST'])
def nova_ordem():
    if 'id_usuario' not in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        nova_os = {
            "cliente_id": int(request.form.get("cliente_id")),
            "veiculo_id": int(request.form.get("veiculo_id")),
            "mecanico_id": int(request.form.get("mecanico_id")) if request.form.get("mecanico_id") else None,
            "descricao_problema": request.form.get("descricao_problema"),
            "status": request.form.get("status"),
            "preco_total": 0.00
        }
        try:
            supabase.table("ordens_servico").insert(nova_os).execute()
            flash('Ordem de Serviço aberta com sucesso!', 'success')
            return redirect(url_for('listar_ordens'))
        except Exception as e:
            flash(f'Erro ao abrir Ordem de Serviço: {e}', 'danger')

    # SELECIONAR CLIENTE: Busca todos os clientes ordenados por nome para popular o formulário
    clientes = supabase.table("clientes").select("id, nome").order("nome").execute().data
    mecanicos = supabase.table("mecânicos").select("id, nome").order("nome").execute().data

    return render_template('nova_os.html', clientes=clientes, mecanicos=mecanicos)


# --- API AUXILIAR: CARREGAR VEÍCULOS POR CLIENTE VIA AJAX ---
@app.route('/api/veiculos/<int:cliente_id>')
def api_veiculos_por_cliente(cliente_id):
    veiculos = supabase.table("veiculos").select("id, marca, modelo, placa").eq("cliente_id", cliente_id).execute().data
    return jsonify(veiculos)


# ==========================================
# 8. EXECUÇÃO DO SERVIDOR LOCAL
# ==========================================
if __name__ == '__main__':
    app.run(debug=True)