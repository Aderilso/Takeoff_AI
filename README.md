# Takeoff AI Multi v2

MVP para extração de tabelas de PDFs usando IA (Gemini) com sistema de presets inteligentes.

## 🚀 Instalação (Windows)

### 1. Pré-requisitos
- Python 3.8+ instalado
- Conta Google Cloud com API Gemini ativada

### 2. Configuração Inicial

1. **Clone ou baixe o projeto** para `D:\POCs\Takeoff_AI_Multi_v2`

2. **Configure a API Key do Gemini:**
   - Copie `config\env_template.txt` para `config\.env`
   - Edite `config\.env` e adicione sua chave:
   ```
   GEMINI_API_KEY=sua_chave_aqui
   ```

3. **Execute o script de instalação:**
   ```cmd
   run.bat
   ```

### 3. Execução
```cmd
run.bat
```

O app abrirá automaticamente no navegador em `http://localhost:8501`

## 📋 Como Usar

### Fluxo Principal
1. **Upload do PDF**: Selecione um arquivo PDF local
2. **Seleção de Página**: Escolha a página (0-index)
3. **Delimitar Crop**: Clique no botão e arraste para definir a área de corte
4. **Salvar Preset**: Escolha o escopo (Global, Por Modelo, Somente neste PDF)
5. **Processar**: Envie para o Gemini e receba os dados em JSON/CSV

### Presets
- **Global**: Aplicado automaticamente em todos os PDFs
- **Por Modelo**: Aplicado apenas em PDFs do mesmo template
- **Somente neste PDF**: Aplicado apenas no documento atual

### Saídas
Os arquivos são salvos em `out/` com timestamp:
- `raw.json`: Resposta bruta do Gemini
- `tabela.jsonl`: Dados em formato JSONL
- `tabela.csv`: Dados em formato CSV (UTF-8)

## 🔧 Troubleshooting

### Problemas de Encoding
- Se houver problemas com caracteres especiais, execute no cmd:
  ```cmd
  chcp 65001
  ```

### Validação de API Key
O sistema valida automaticamente a chave da API Gemini na inicialização:

**Validações realizadas:**
- ✅ Verifica se o arquivo `config\.env` existe
- ✅ Confirma se a variável `GEMINI_API_KEY` está definida
- ✅ Testa se a chave é válida fazendo uma requisição de teste
- ✅ Verifica se a API está acessível

**Mensagens de erro possíveis:**
- ❌ **Chave não encontrada**: Arquivo `.env` não existe ou chave está vazia
- ❌ **Chave inválida**: Chave incorreta ou API não ativada
- ❌ **Erro de conectividade**: Problemas de rede ou quota excedida

### API Key não encontrada
- Verifique se o arquivo `config\.env` existe
- Copie `config\env_template.txt` para `config\.env` se necessário
- Confirme que a variável `GEMINI_API_KEY` está definida

### PDF não carrega
- Verifique se o PDF não está corrompido
- Teste com PDFs menores (menos de 10MB)

### Erro no Gemini
- Verifique sua quota de API
- Confirme se a API está ativada no Google Cloud Console

## 📁 Estrutura do Projeto

```
D:\POCs\Takeoff_AI_Multi_v2\
├── app/
│   ├── app.py              # Aplicação principal Streamlit
│   ├── presets.py          # Gerenciamento de presets
│   ├── gemini_client.py    # Cliente da API Gemini
│   ├── pdf_utils.py        # Utilitários para PDF
│   └── ui_state.py         # Estado da interface
├── config/
│   ├── presets.json        # Presets salvos
│   └── env_template.txt    # Template de configuração
├── out/                    # Arquivos de saída
├── requirements.txt        # Dependências Python
├── run.bat                # Script de execução
└── README.md              # Este arquivo
```

## 🎯 Funcionalidades

- ✅ Upload e visualização de PDFs
- ✅ Sistema de presets inteligentes
- ✅ Cropper interativo
- ✅ Integração com Gemini AI
- ✅ Exportação em múltiplos formatos
- ✅ Interface responsiva em português
- ✅ Detecção automática de tabelas (opcional)

## 📝 Notas Técnicas

- Presets são salvos em coordenadas relativas (0-1) para independência de DPI
- Suporte a múltiplas páginas com aplicação automática de presets
- Tratamento robusto de erros da API
- Interface em português brasileiro
- Compatibilidade total com Windows
