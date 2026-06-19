<div align="center">

# Job Matcher

### Cansado de mandar currículo no escuro?

O Job Matcher busca vagas, calcula sua compatibilidade real e manda os melhores matches por e-mail — automaticamente, enquanto você faz outra coisa.

<br>

[![Download Windows](https://img.shields.io/badge/⬇️%20Download%20para%20Windows-v0.0.1-FFB300?style=for-the-badge)](https://github.com/cherohn/job-matcher/releases/tag/v0.0.1)

*Gratuito · Sem instalação · Traga suas próprias APIs*

</div>

---

## Por que isso existe

Procurar emprego manualmente é frustrante por um motivo específico: você não sabe se a vaga vale seu tempo antes de ler tudo, pesquisar a empresa, montar a candidatura — e descobrir, depois de dias, que ela pedia Angular e você é backend.

Eu queria uma ferramenta que me dissesse:

> *"Essa vaga aqui tá boa — mas ela pede React e você é backend, então o fit real é 72%, não 90%. Já essa outra, a stack bate, o nível bate, e ainda dá pra melhorar seu currículo nesses dois pontos específicos."*

Não encontrei nada assim. Então construí.

---

## Download

<div align="center">

### ⬇️ [Clique aqui para baixar o Job Matcher para Windows](https://github.com/cherohn/job-matcher/releases/tag/v0.0.1)

</div>

```
1. Baixe JobMatcherApp.zip na página de releases
2. Extraia o zip
3. Execute JobMatcherApp.exe
```

Não precisa instalar Python, Node, nem nada. Só baixar e rodar.

> **Requisito:** Windows 10 ou superior

---

## Interface

### Painel principal
![Painel de busca e monitoramento](assets/painel-principal.png)

Configure quantas vagas analisar por varredura, defina o score mínimo de compatibilidade e o intervalo entre buscas. O log mostra só eventos relevantes — sem spam.

---

### Configuração de credenciais
![Tela de configuração — credenciais e perfil](assets/configuracao-credenciais.png)

Suas chaves de API e senha do Gmail são armazenadas com **DPAPI do Windows** — nunca em texto puro no disco.

---

### Configuração de perfil e filtros
![Tela de configuração — áreas, senioridade e modalidade](assets/configuracao-filtros.png)

Selecione as áreas, níveis de senioridade e modalidades de trabalho que fazem sentido pra você. O app só busca o que você quer.

---

### Filtros avançados
![Tela de configuração — localização, empresas-alvo e queries](assets/configuracao-avancada.png)

Filtros de localização aceitos, empresas-alvo opcionais e queries manuais extras para afinar ainda mais a busca.

---

## O que ele faz

- Busca vagas no Google usando os termos e filtros que você configurar
- Lê e filtra o conteúdo real das páginas de vaga
- Calcula um **score de compatibilidade** entre a vaga e o seu currículo/perfil usando IA
- Manda os melhores matches por **e-mail automaticamente** no intervalo definido
- Gera uma **análise honesta por vaga**:
  - pontos fortes do seu perfil para aquela posição
  - o que não bate e por quê
  - sugestões específicas para melhorar o currículo pra aquela vaga
- Evita repetição com **cache local** de vagas já analisadas
- Salva **relatórios locais** em `reports/` para consulta posterior

---

## Como funciona

```
Você configura os termos de busca e filtros
              │
              ▼
    Serper busca vagas no Google
              │
              ▼
   App lê o conteúdo real de cada vaga
              │
              ▼
  Groq AI compara vaga × currículo × perfil
              │
              ▼
   Score calculado → abaixo do mínimo, descarta
              │
              ▼
  Melhores matches enviados por Gmail com análise
              │
              ▼
  Relatório salvo + cache atualizado
```

---

## O que você precisa fornecer

O app não cobra nada. Você traz suas próprias credenciais:

| Credencial | Para que serve | Como obter |
|---|---|---|
| **Groq API Key** | IA que analisa as vagas | [console.groq.com/keys](https://console.groq.com/keys) — gratuito |
| **Serper API Key** | Busca no Google | [serper.dev](https://serper.dev) — gratuito |
| **Gmail + Senha de app** | Envio dos matches | [Instruções no guia](GUIA_USUARIO.md) |
| **Arquivo de perfil (.txt)** | Seu perfil profissional | Você escreve |
| **Currículo (.pdf)** | Base para o score de fit | Seu currículo atual |

---

## Primeiros passos

1. Abra `JobMatcherApp.exe`
2. Clique em **Configurar**
3. Preencha suas credenciais (Groq, Serper, Gmail)
4. Selecione seu arquivo de perfil `.txt` e currículo `.pdf`
5. Escolha as áreas, senioridades e modalidades desejadas
6. Configure os filtros de localização e queries extras se quiser
7. Clique em **Salvar configuração**
8. Clique em **E-mail teste** para confirmar que está chegando
9. Clique em **Varredura única** para testar uma vez
10. Clique em **Iniciar** para monitoramento contínuo

Guia completo com prints passo a passo: [GUIA_USUARIO.md](GUIA_USUARIO.md)

---

## Segurança

Credenciais sensíveis (chaves de API e senha do Gmail) são protegidas com **DPAPI do Windows** antes de serem salvas — a proteção é vinculada ao seu usuário Windows.

Nunca compartilhe ou publique:
- `config.json`
- `job_cache.json`
- A pasta `user_data/` ou `%APPDATA%\JobMatcher`
- Prints da tela de configuração

Se alguma credencial vazar, revogue imediatamente em Groq, Serper ou Google e gere uma nova.

---

## Rodando pelo código-fonte

```bash
git clone https://github.com/cherohn/job-matcher.git
cd job-matcher
pip install -r requirements.txt
python app_desktop.py
```

Para gerar o executável:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

---

## Estrutura do projeto

```
job-matcher/
├── app_desktop.py           # Interface desktop (CustomTkinter)
├── main.py                  # Lógica principal de varredura
├── config/
│   └── settings.py          # Configurações globais
├── core/
│   ├── matcher.py           # Score de fit via Groq AI
│   ├── resume_parser.py     # Leitura do currículo PDF
│   ├── cache.py             # Cache de vagas já analisadas
│   ├── report.py            # Geração de relatórios locais
│   ├── secure_store.py      # Armazenamento seguro (DPAPI)
│   └── user_config.py       # Gerenciamento de configurações
├── notifier/
│   └── email_notifier.py    # Envio de e-mail com os matches
├── scrapers/                # Leitura e filtragem de páginas
├── GUIA_USUARIO.md
└── requirements.txt
```

---

## Limitações conhecidas (v0.0.1)

- Monitoramento contínuo exige que o app fique aberto e o computador ligado
- Cache local — se deletar `job_cache.json`, vagas antigas podem reaparecer
- Proteção de credenciais com DPAPI funciona só no Windows por enquanto
- Se um site de vagas mudar a URL, a mesma vaga pode parecer nova

---

## Roadmap

- [ ] Instalador com setup guiado
- [ ] Mais fontes de busca além do Google/Serper
- [ ] Deduplicação mais robusta de vagas
- [ ] Agendamento em background sem precisar manter o app aberto
- [ ] Exportação de relatório em PDF
- [ ] Suporte a credenciais seguras fora do Windows

---

## Aviso

O Job Matcher não garante entrevistas, ofertas ou emprego. É um assistente local que ajuda a encontrar vagas relevantes e melhorar o direcionamento do currículo usando suas próprias credenciais e dados.

---

## Licença

MIT — pode usar, modificar e distribuir livremente.

---

<div align="center">

Feito por **Matheus Garcez** · [github.com/cherohn](https://github.com/cherohn) · [LinkedIn](https://linkedin.com/in/matheus-garcez-172377249)

</div>
