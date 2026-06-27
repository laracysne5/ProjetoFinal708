import os
import datetime
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
app.secret_key = '12345' # Chave de segurança para cookies e sessões


# ==========================================
# 2. FUNÇÕES DE PROTEÇÃO DE ACESSO (TRAVAS)
# ==========================================
def verificar_acesso(perfis_permitidos):
    """Função auxiliar para validar se o usuário está logado e possui o perfil correto."""
    if 'id_usuario' not in session:
        return False, redirect(url_for('index'))
    
    if session.get('perfil') not in perfis_permitidos:
        flash('⚠️ Acesso negado! Seu perfil não tem permissão para acessar esta página.', 'danger')
        return False, redirect(url_for('dashboard'))
        
    return True, None


# ==========================================
# 3. SISTEMA DE LOGIN, LOGOUT E CADASTRO
# ==========================================

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        senha = request.form.get('senha')
        
        try:
            resposta = supabase.table('usuarios').select('id, nome, email, perfil').eq('email', email).eq('senha', senha).execute()
            if len(resposta.data) > 0:
                usuario_logado = resposta.data[0]
                session['id_usuario'] = usuario_logado['id']
                session['nome_usuario'] = usuario_logado['nome']
                session['email_usuario'] = usuario_logado['email']
                session['perfil'] = usuario_logado.get('perfil', 'CLIENTE').upper()
                
                return redirect(url_for('dashboard'))
            else:
                flash('E-mail ou senha incorretos! Tente novamente.', 'danger')
        except Exception as e:
            print(f"❌ Erro de conexão no Login: {e}")
            flash('Erro ao conectar com o banco de dados.', 'danger')
            
    return render_template('index.html')


@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        email_tratado = request.form.get("email", "").strip().lower()
        
        novo_usuario = {
            "nome": request.form.get("nome"),
            "email": email_tratado,
            "senha": request.form.get("senha"),
            "perfil": "CLIENTE",
            "ativo": True
        }
        
        try:
            usuario_existe = supabase.table("usuarios").select("id").eq("email", email_tratado).execute().data
            if usuario_existe:
                flash('Este e-mail já está cadastrado no sistema!', 'warning')
                return render_template('cadastro.html')
                
            supabase.table("usuarios").insert(novo_usuario).execute()
            flash('Sua conta de Cliente foi criada com sucesso! Faça login abaixo.', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            print(f"❌ Erro ao cadastrar cliente no Supabase: {e}")
            flash('Erro ao realizar o cadastro. Tente novamente mais tarde.', 'danger')
            
    return render_template('cadastro.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Você saiu do sistema.', 'info')
    return redirect(url_for('index'))


# ==========================================
# 4. PAINEL PRINCIPAL DINÂMICO (DASHBOARD)
# ==========================================

@app.route('/dashboard')
def dashboard():
    if 'id_usuario' not in session:
        return redirect(url_for('index'))
        
    perfil = session.get('perfil')
    
    if perfil == 'CLIENTE':
        ordens_cliente = []
        try:
            email_logado = session.get('email_usuario')
            cliente_dados = supabase.table("clientes").select("id").eq("email", email_logado).execute().data
            
            if cliente_dados:
                id_cliente_banco = cliente_dados[0]['id']
                ordens_cliente = supabase.table("ordens_servico").select(
                    "id, status, descricao_problema, valor_total, data_abertura, veiculos(marca, modelo, placa)"
                ).eq("cliente_id", id_cliente_banco).order("id", desc=True).execute().data
        except Exception as e:
            print(f"❌ Erro ao carregar painel do cliente: {e}")
            
        return render_template('dashboard_cliente.html', ordens=ordens_cliente)
        
    try:
        clientes = supabase.table("clientes").select("id, nome, email, telefone, veiculos(id)").execute().data
        
        pecas = supabase.table("pecas").select("id, quantidade_estoque").execute().data
        total_pecas = sum(p['quantidade_estoque'] for p in pecas) if pecas else 0
        
        ordens = supabase.table("ordens_servico").select(
            "id, status, descricao_problema, valor_total, data_abertura, clientes(nome), veiculos(modelo, placa)"
        ).order("id", desc=True).execute().data
        
        os_abertas = len([o for o in ordens if o['status'] == 'ABERTA']) if ordens else 0
        os_andamento = len([o for o in ordens if o['status'] == 'EM_ANDAMENTO']) if ordens else 0
        os_aguardando = len([o for o in ordens if o['status'] == 'AGUARDANDO_PEÇAS']) if ordens else 0
        
    except Exception as e:
        print(f"⚠️ Aviso: Algumas tabelas gerenciais estão vazias ou inacessíveis ({e})")
        total_pecas = 0
        ordens = []
        os_abertas = 0
        os_andamento = 0
        os_aguardando = 0
        
    return render_template(
        'dashboard.html', 
        clientes=clientes, 
        total_pecas=total_pecas, 
        ordens=ordens, 
        os_abertas=os_abertas,
        os_andamento=os_andamento + os_aguardando
    )


# ==========================================
# 5. MÓDULO: CLIENTES E VEÍCULOS
# ==========================================

@app.route('/clientes', methods=['GET'])
def listar_clientes():
    permitido, redirecionamento = verificar_acesso(['ADMIN', 'FUNCIONARIO'])
    if not permitido: return redirecionamento

    try:
        resposta = supabase.table("clientes").select("id, nome, email, telefone, veiculos(marca, modelo, placa)").execute()
        lista_clientes = resposta.data 
        clientes_select = supabase.table("clientes").select("id, nome").order("nome").execute().data
    except Exception as e:
        print(f"❌ Erro ao listar clientes: {e}")
        lista_clientes = []
        clientes_select = []

    return render_template('clientes.html', clientes=lista_clientes, clientes_select=clientes_select)


@app.route('/cadastrar_cliente', methods=['POST'])
def cadastrar_cliente():
    permitido, redirecionamento = verificar_acesso(['ADMIN', 'FUNCIONARIO'])
    if not permitido: return redirecionamento

    novo_cliente = {
        "nome": request.form.get("nome"),
        "email": request.form.get("email", "").strip().lower(),
        "telefone": request.form.get("telefone")
        # A linha "ativo": True foi removida daqui!
    }
    try:
        print(f"📊 DADOS DO CLIENTE SENDO ENVIADOS: {novo_cliente}")
        supabase.table("clientes").insert(novo_cliente).execute()
        flash("Cliente adicionado com sucesso!", "success")
    except Exception as e:
        print("\n❌--- ERRO DETALHADO DO SUPABASE (CLIENTES) ---")
        print(e)
        print("------------------------------------------------\n")
        flash("Erro ao salvar cliente no banco.", "danger")
        
    return redirect(url_for('listar_clientes'))

@app.route('/cadastrar_veiculo', methods=['POST'])
def cadastrar_veiculo():
    permitido, redirecionamento = verificar_acesso(['ADMIN', 'FUNCIONARIO'])
    if not permitido: return redirecionamento

    novo_veiculo = {
        "marca": request.form.get("marca"),
        "modelo": request.form.get("modelo"),
        "placa": request.form.get("placa"),
        "cliente_id": int(request.form.get("cliente_id"))
        # Removido a linha "ativo": True por segurança, seguindo o padrão das outras tabelas
    }
    try:
        print(f"📊 DADOS DO VEÍCULO SENDO ENVIADOS: {novo_veiculo}")
        supabase.table("veiculos").insert(novo_veiculo).execute()
        flash("Veículo vinculado com sucesso!", "info")
    except Exception as e:
        print("\n❌--- ERRO DETALHADO DO SUPABASE (VEÍCULOS) ---")
        print(e) # Mostra o erro real no terminal do VS Code
        print("------------------------------------------------\n")
        flash("Erro ao salvar veículo no banco.", "danger")
        
    return redirect(url_for('listar_clientes'))


# ==========================================
# 6. MÓDULO: MECÂNICOS
# ==========================================

@app.route('/mecanicos', methods=['GET', 'POST'])
def gerenciar_mecanicos():
    permitido, redirecionamento = verificar_acesso(['ADMIN'])
    if not permitido: return redirecionamento

    if request.method == 'POST':
        novo_mecanico = {
            "nome": request.form.get("nome"),
            "especialidade": request.form.get("especialidade"),
            "telefone": request.form.get("telefone")
            # A linha "ativo": True foi removida daqui!
        }
        try:
            print(f"📊 DADOS DO MECÂNICO SENDO ENVIADOS: {novo_mecanico}")
            supabase.table("mecânicos").insert(novo_mecanico).execute()
            flash("Mecânico integrado à equipe!", "success")
        except Exception as e:
            print("\n❌--- ERRO DETALHADO DO SUPABASE (MECÂNICOS) ---")
            print(e)
            print("------------------------------------------------\n")
            flash("Erro ao salvar mecânico.", "danger")
        return redirect(url_for('gerenciar_mecanicos'))

    try:
        lista_mecanicos = supabase.table("mecânicos").select("*").order("nome").execute().data
    except Exception as e:
        print(f"❌ Tabela de mecânicos com erro: {e}")
        lista_mecanicos = []
        
    return render_template('mecanicos.html', mecanicos=lista_mecanicos)
# ==========================================
# 7. MÓDULO: ESTOQUE DE PEÇAS
# ==========================================

@app.route('/estoque', methods=['GET'])
def listar_estoque():
    permitido, redirecionamento = verificar_acesso(['ADMIN', 'FUNCIONARIO'])
    if not permitido: return redirecionamento
        
    try:
        lista_pecas = supabase.table("pecas").select("*").order("nome").execute().data
    except Exception as e:
        print(f"❌ Tabela de peças com erro: {e}")
        lista_pecas = []
        
    return render_template('estoque.html', pecas=lista_pecas)


@app.route('/estoque/adicionar', methods=['POST'])
def adicionar_peca_estoque():
    permitido, redirecionamento = verificar_acesso(['ADMIN', 'FUNCIONARIO'])
    if not permitido: return redirecionamento
        
    nova_peca = {
        "nome": request.form.get("nome"),
        "codigo": request.form.get("codigo"),
        "quantidade_estoque": int(request.form.get("quantidade", 0)),
        "preco_venda": float(request.form.get("preco", 0.00))
        # A linha "custo" foi removida daqui!
    }
    try:
        print(f"📊 DADOS DA PEÇA SENDO ENVIADOS: {nova_peca}")
        supabase.table("pecas").insert(nova_peca).execute()
        flash("Nova peça adicionada com sucesso ao almoxarifado!", "success")
    except Exception as e:
        print("\n❌--- ERRO DETALHADO DO SUPABASE (ESTOQUE) ---")
        print(e)
        print("----------------------------------------------\n")
        flash("Erro ao salvar o item no estoque.", "danger")
        
    return redirect(url_for('listar_estoque'))


@app.route('/estoque/editar/<int:peca_id>', methods=['POST'])
def editar_quantidade_estoque(peca_id):
    permitido, redirecionamento = verificar_acesso(['ADMIN', 'FUNCIONARIO'])
    if not permitido: return redirecionamento
        
    nova_qtd = int(request.form.get("nova_quantidade", 0))
    try:
        supabase.table("pecas").update({"quantidade_estoque": nova_qtd}).eq("id", peca_id).execute()
        flash("Quantidade em estoque sincronizada com sucesso!", "success")
    except Exception as e:
        print(f"❌ Erro ao editar saldo de peças: {e}")
        flash("Não foi possível atualizar a quantidade.", "danger")
        
    return redirect(url_for('listar_estoque'))


# ==========================================
# 8. MÓDULO: ORDENS DE SERVIÇO (VERSÃO DIAGNÓSTICO UNIFICADA)
# ==========================================

@app.route('/os', methods=['GET'])
def listar_ordens():
    permitido, redirecionamento = verificar_acesso(['ADMIN', 'FUNCIONARIO'])
    if not permitido: return redirecionamento
        
    try:
        # CORREÇÃO AQUI: Ajustado para as colunas reais do seu banco (descricao_problema e mecânicos)
        resposta = supabase.table("ordens_servico").select(
            "id, status, descricao_problema, valor_total, data_abertura, clientes(nome), veiculos(marca, modelo, placa), mecânicos(nome)"
        ).order("id", desc=True).execute()
        lista_os = resposta.data
    except Exception as e:
        print("\n❌--- ERRO AO LISTAR ORDENS DE SERVIÇO ---")
        print(e)  # Se ainda der erro, vai mostrar o culpado exato no seu terminal
        print("----------------------------------------\n")
        lista_os = []
        
    return render_template('ordens.html', ordens=lista_os)


@app.route('/os/nova', methods=['GET', 'POST'])
def nova_ordem():
    permitido, redirecionamento = verificar_acesso(['ADMIN', 'FUNCIONARIO'])
    if not permitido: return redirecionamento

    if request.method == 'POST':
        # Tenta capturar o problema pelos dois nomes possíveis que podem estar no HTML
        problema = request.form.get("problema_relatado") or request.form.get("descricao_problema")
        
        # Se mesmo assim vier vazio, define um texto padrão para não quebrar a restrição NOT NULL
        if not problema or problema.strip() == "":
            problema = "Problema não detalhado pelo atendente"

        nova_os = {
            "cliente_id": int(request.form.get("cliente_id")),
            "veiculo_id": int(request.form.get("veiculo_id")),
            "mecanico_id": int(request.form.get("mecanico_id")) if request.form.get("mecanico_id") else None,
            "descricao_problema": problema, # Garante o envio do texto tratado
            "status": request.form.get("status", "ABERTA").upper(),
            "data_abertura": datetime.date.today().isoformat(),
            "valor_total": 0.00
        }
        try:
            print(f"📊 DADOS SENDO ENVIADOS: {nova_os}")
            supabase.table("ordens_servico").insert(nova_os).execute()
            flash("Ordem de Serviço criada com sucesso!", "success")
            return redirect(url_for('listar_ordens'))
        except Exception as e:
            print("\n❌--- ERRO DETALHADO DO SUPABASE ---")
            print(e)
            print("------------------------------------\n")
            flash("Erro ao registrar Ordem de Serviço no banco.", "danger")

    clientes = supabase.table("clientes").select("id, nome").order("nome").execute().data
    try:
        mecanicos = supabase.table("mecânicos").select("id, nome").order("nome").execute().data
    except:
        mecanicos = []
    return render_template('nova_os.html', clientes=clientes, mecanicos=mecanicos)

@app.route('/api/veiculos/<int:cliente_id>')
def api_veiculos_por_cliente(cliente_id):
    if 'id_usuario' not in session:
        return jsonify([])
    veiculos = supabase.table("veiculos").select("id, marca, modelo, placa").eq("cliente_id", cliente_id).execute().data
    return jsonify(veiculos)


# ==========================================
# 9. LANÇAMENTO DE ITENS E BAIXA AUTOMÁTICA
# ==========================================

@app.route('/os/detalhes/<int:os_id>', methods=['GET'])
def detalhes_os(os_id):
    if 'id_usuario' not in session:
        return redirect(url_for('index'))
        
    try:
        os_dados = supabase.table("ordens_servico").select(
            "id, status, descricao_problema, valor_total, data_abertura, clientes(nome, email, telefone), veiculos(marca, modelo, placa)"
        ).eq("id", os_id).single().execute().data

        if session.get('perfil') == 'CLIENTE' and os_dados['clientes']['email'] != session.get('email_usuario'):
            flash("Acesso não autorizado a esta ordem de serviço.", "danger")
            return redirect(url_for('dashboard'))

        itens = supabase.table("os_itens").select("*").eq("os_id", os_id).execute().data
        pecas_estoque = supabase.table("pecas").select("id, nome, quantidade_estoque, preco_venda").execute().data
    except Exception as e:
        print(f"❌ Erro ao coletar detalhes da OS: {e}")
        flash("Ordem de serviço não encontrada.", "danger")
        return redirect(url_for('dashboard'))

    return render_template('detalhes_os.html', os=os_dados, itens=itens, pecas=pecas_estoque)


@app.route('/os/adicionar_item/<int:os_id>', methods=['POST'])
def adicionar_item_os(os_id):
    permitido, redirecionamento = verificar_acesso(['ADMIN', 'FUNCIONARIO'])
    if not permitido:
        return redirecionamento

    tipo = request.form.get("tipo", "").upper()
    quantidade = int(request.form.get("quantidade", 1))

    try:
        # ===============================
        # SE FOR PEÇA
        # ===============================
        if tipo == "PEÇA":
            peca_id = request.form.get("peca_id")

            peca_dados = supabase.table("pecas") \
                .select("*") \
                .eq("id", peca_id) \
                .single() \
                .execute().data

            descricao = peca_dados["nome"]
            preco_unitario = float(peca_dados["preco_venda"])

            # Verifica estoque
            if peca_dados["quantidade_estoque"] < quantidade:
                flash(
                    f"Estoque insuficiente! Restam apenas {peca_dados['quantidade_estoque']} unidades.",
                    "danger"
                )
                return redirect(url_for("detalhes_os", os_id=os_id))

            # Atualiza estoque
            novo_estoque = peca_dados["quantidade_estoque"] - quantidade

            supabase.table("pecas") \
                .update({"quantidade_estoque": novo_estoque}) \
                .eq("id", peca_id) \
                .execute()

            # Alerta estoque baixo
            if novo_estoque <= 3:
                flash(
                    f"⚠️ Estoque baixo da peça '{descricao}'. Restam {novo_estoque} unidades.",
                    "warning"
                )

            tipo_banco = "Peca"

        # ===============================
        # SE FOR SERVIÇO
        # ===============================
        else:
            peca_id = None
            descricao = request.form.get("descricao_servico")
            preco_unitario = float(request.form.get("preco_servico", 0))
            tipo_banco = "Servico"

        # Calcula total do item
        preco_total = preco_unitario * quantidade

        # Cria item da OS
        novo_item = {
            "os_id": os_id,
            "tipo": tipo_banco,
            "descricao": descricao if descricao else "Item de Serviço",
            "peca_id": int(peca_id) if peca_id else None,
            "quantidade": quantidade,
            "preco_unitario": preco_unitario,
            "preco_total": preco_total
        }

        # Salva item
        supabase.table("os_itens").insert(novo_item).execute()

        # Busca todos os itens da OS
        todos_itens = supabase.table("os_itens") \
            .select("preco_total") \
            .eq("os_id", os_id) \
            .execute().data

        # Soma total da OS
        novo_total_os = sum(float(item["preco_total"]) for item in todos_itens)

        # Atualiza total da ordem
        supabase.table("ordens_servico") \
            .update({"valor_total": novo_total_os}) \
            .eq("id", os_id) \
            .execute()

        flash("Item adicionado com sucesso!", "success")

    except Exception as e:
        print(f"\n❌ ERRO AO ADICIONAR ITEM NA OS {os_id}:")
        print(e)
        print("--------------------------------------\n")
        flash("Erro ao processar item da OS.", "danger")

    return redirect(url_for("detalhes_os", os_id=os_id))


# ==========================================
# 10. MÓDULO DE RELATÓRIOS (APENAS ADMIN)
# ==========================================

@app.route('/relatorios', methods=['GET'])
def painel_relatorios():
    permitido, redirecionamento = verificar_acesso(['ADMIN'])
    if not permitido: return redirecionamento
    return render_template('relatorios.html')


@app.route('/relatorios/os-abertas')
def relatorio_os_abertas():
    permitido, redirecionamento = verificar_acesso(['ADMIN'])
    if not permitido: return redirecionamento
    
    try:
        status_ativos = ['ABERTA', 'EM_ANDAMENTO', 'AGUARDANDO_PEÇAS']
        resposta = supabase.table("ordens_servico").select(
            "id, status, descricao_problema, valor_total, data_abertura, clientes(nome), veiculos(marca, modelo, placa)"
        ).in_("status", status_ativos).order("id", desc=True).execute()
        ordens = resposta.data
    except Exception as e:
        print(f"❌ Erro ao gerar relatório de OS Abertas: {e}")
        ordens = []
        
    return render_template('relatorio_os_abertas.html', ordens=ordens)


@app.route('/relatorios/os-concluidas', methods=['GET', 'POST'])
def relatorio_os_concluidas():
    permitido, redirecionamento = verificar_acesso(['ADMIN'])
    if not permitido: return redirecionamento
        
    ordens = []
    data_inicio = request.values.get('data_inicio', '')
    data_fim = request.values.get('data_fim', '')
    faturamento_periodo = 0.0

    if data_inicio and data_fim:
        try:
            resposta = supabase.table("ordens_servico").select(
                "id, status, descricao_problema, valor_total, data_conclusao, clientes(nome), veiculos(marca, modelo, placa)"
            ).eq("status", "CONCLUÍDA").gte("data_conclusao", data_inicio).lte("data_conclusao", data_fim).order("data_conclusao", desc=True).execute()
            
            ordens = resposta.data
            faturamento_periodo = sum(float(o['valor_total']) for o in ordens if o['valor_total'] is not None)
        except Exception as e:
            print(f"❌ Erro ao filtrar OS concluídas: {e}")

    return render_template('relatorio_os_concluidas.html', ordens=ordens, data_inicio=data_inicio, data_fim=data_fim, faturamento=faturamento_periodo)


@app.route('/relatorios/estoque-baixo')
def relatorio_estoque_baixo():
    permitido, redirecionamento = verificar_acesso(['ADMIN'])
    if not permitido: return redirecionamento
        
    try:
        LIMITE_CRITICO = 5
        resposta = supabase.table("pecas").select("*").lte("quantidade_estoque", LIMITE_CRITICO).order("quantidade_estoque").execute()
        pecas = resposta.data
    except Exception as e:
        print(f"❌ Erro ao gerar relatório de estoque: {e}")
        pecas = []
        
    return render_template('relatorio_estoque_baixo.html', pecas=pecas)

@app.route('/os/excluir/<int:os_id>', methods=['POST'])
def excluir_ordem(os_id):
    # 🔒 TRAVA DE SEGURANÇA: Apenas ADMIN pode rodar essa rota de exclusão
    permitido, redirecionamento = verificar_acesso(['ADMIN'])
    if not permitido: 
        flash("Acesso negado. Apenas administradores podem excluir ordens.", "danger")
        return redirecionamento

    try:
        # Limpa os itens vinculados para evitar erro de Foreign Key
        supabase.table("os_itens").delete().eq("os_id", os_id).execute()
        
        # Exclui a OS principal
        supabase.table("ordens_servico").delete().eq("id", os_id).execute()
        
        flash(f"Ordem de Serviço #{os_id} foi excluída com sucesso!", "success")
    except Exception as e:
        print("\n❌--- ERRO AO EXCLUIR ORDEM DE SERVIÇO ---")
        print(e)
        print("----------------------------------------\n")
        flash("Erro ao tentar excluir a Ordem de Serviço no banco.", "danger")
        
    return redirect(url_for('listar_ordens'))


if __name__ == '__main__':
    app.run(debug=True)