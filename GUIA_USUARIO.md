# Guia do Usuario - Job Matcher

Este guia explica como instalar, configurar, usar e entender o Job Matcher.

## 1. O que o sistema faz

O Job Matcher procura vagas usando Google via Serper, le as paginas encontradas, compara cada vaga com o perfil do usuario usando IA da Groq e envia por e-mail os melhores resultados.

Para cada vaga analisada, ele gera:

- score de compatibilidade de 0 a 100.
- pontos fortes do usuario para aquela vaga.
- gaps reais.
- resumo curto do motivo do score.
- sugestao de headline para curriculo direcionado.
- habilidades e experiencias que devem aparecer primeiro no curriculo.
- ajustes honestos para deixar o curriculo mais profissional para aquela vaga.

O sistema nao cria candidatura automaticamente e nao garante contratacao. Ele ajuda a encontrar vagas melhores e a adaptar o curriculo com base no que o usuario realmente sabe.

## 2. O que precisa antes de usar

Voce precisa de:

- uma API key da Groq.
- uma API key do Serper.
- uma conta Gmail.
- uma senha de app do Google para envio de e-mail.
- um arquivo `.txt` com informacoes sobre voce.
- um curriculo em PDF.

## 3. Como pegar API key da Groq

1. Acesse `https://console.groq.com/keys`.
2. Entre ou crie uma conta.
3. Clique para criar uma nova API key.
4. Copie a chave gerada.
5. No Job Matcher, clique em `Configurar`.
6. Cole a chave no campo `API de IA Groq`.

O modelo padrao usado pelo app e `llama-3.3-70b-versatile`.

## 4. Como pegar API key do Serper

1. Acesse `https://serper.dev`.
2. Crie uma conta.
3. Abra a area de API key.
4. Copie a chave.
5. No Job Matcher, clique em `Configurar`.
6. Cole a chave no campo `API Serper`.

O Serper e usado para pesquisar vagas no Google de forma automatizada. Sem essa chave, a fonte principal de busca nao funciona.

## 5. Como criar senha de app do Gmail

A senha de app nao e sua senha normal do Gmail. Ela e uma senha separada, criada so para aplicativos.

1. Acesse `https://myaccount.google.com/security`.
2. Entre na sua conta Google.
3. Ative a `Verificacao em duas etapas`, se ainda nao estiver ativa.
4. Depois de ativar, procure por `Senhas de app`.
5. Crie uma nova senha de app para `Mail` ou use um nome como `Job Matcher`.
6. O Google vai mostrar uma senha de 16 caracteres.
7. Copie essa senha.
8. No Job Matcher, cole no campo `Senha de app do Gmail`.

No campo `Gmail remetente`, coloque o Gmail que vai enviar as mensagens.

No campo `E-mail que recebera os matches`, coloque o e-mail que vai receber os resultados. Pode ser o mesmo Gmail.

## 6. Como preparar o arquivo TXT de perfil

Crie um arquivo `.txt` com tudo que voce sabe sobre voce profissionalmente.

Inclua:

- nome.
- cargo alvo.
- localizacao.
- e-mail.
- LinkedIn.
- GitHub ou portfolio.
- resumo profissional.
- tecnologias.
- experiencias.
- projetos.
- formacao.
- certificacoes.
- idiomas.
- conquistas.
- tipos de vaga que voce quer.
- tipos de vaga que voce nao quer.

Quanto mais claro for esse arquivo, melhor a IA consegue comparar seu perfil com as vagas.

## 7. Como configurar no app

1. Abra `JobMatcherApp.exe`.
2. Clique em `Configurar`.
3. Preencha Groq, Serper, Gmail, senha de app e e-mail destino.
4. Selecione o arquivo `.txt` do perfil.
5. Selecione o PDF do curriculo.
6. Edite os termos de busca, um por linha.
7. Clique em `Salvar configuracao`.
8. Clique em `E-mail teste` para confirmar se o envio funciona.
9. Clique em `Varredura unica` para testar uma busca.
10. Clique em `Iniciar` para deixar monitorando em intervalos.

## 8. Onde as informacoes ficam salvas

As configuracoes sao persistentes.

No Windows, o app tenta salvar em:

```text
%APPDATA%\JobMatcher\config.json
%APPDATA%\JobMatcher\job_cache.json
%APPDATA%\JobMatcher\documents\
```

Se o Windows bloquear essa pasta, o app usa:

```text
user_data\config.json
user_data\job_cache.json
user_data\documents\
```

O arquivo `config.json` guarda a configuracao. Os arquivos selecionados pelo usuario sao copiados para `documents`.

## 9. Seguranca

As chaves sensiveis sao:

- API key da Groq.
- API key do Serper.
- senha de app do Gmail.

No Windows, o app salva esses campos protegidos com DPAPI, a protecao nativa do Windows vinculada ao usuario logado. Isso significa que o arquivo salvo nao deve expor as chaves em texto puro.

Importante:

- Nao envie sua pasta `%APPDATA%\JobMatcher` para outras pessoas.
- Nao publique `config.json`.
- Nao publique `job_matcher.log`.
- Nao compartilhe prints da tela de configuracao.
- Se suspeitar vazamento, revogue a chave na Groq, revogue a chave no Serper e apague a senha de app no Google.
- A protecao DPAPI vale para o Windows e para o usuario logado. Em outros sistemas, a protecao pode depender das permissoes do arquivo.

O executavel distribuido nao deve conter credenciais pessoais fixas.

## 10. Como a memoria de vagas repetidas funciona

O Job Matcher salva vagas ja analisadas em `job_cache.json`.

Enquanto esse arquivo existir, o sistema evita analisar novamente a mesma vaga quando o identificador da vaga for igual.

Limitacoes importantes desta versao:

- Se voce apagar `job_cache.json`, o sistema pode repetir vagas antigas.
- Se voce mover o app para outro computador sem levar a pasta de dados, a memoria de vagas analisadas nao acompanha.
- Se o site mudar a URL ou o identificador da vaga, a mesma vaga pode aparecer como nova.
- Se o computador dormir, desligar ou perder internet, o app nao monitora durante esse periodo.
- Para acompanhar vagas continuamente, mantenha o sistema aberto, acordado e com internet.

Em resumo: a memoria local ajuda a evitar repeticao, mas ela depende do arquivo local e do app estar rodando nos horarios de varredura.

## 11. Como o sistema funciona por dentro

1. O app carrega `config.json`.
2. O app monta termos de busca.
3. O Serper pesquisa vagas no Google.
4. O sistema baixa e filtra paginas de vagas.
5. Vagas repetidas sao ignoradas usando `job_cache.json`.
6. O perfil do usuario e montado com TXT + PDF.
7. A Groq analisa perfil contra descricao da vaga.
8. O score e limitado por regras conservadoras para evitar exagero.
9. Resultados acima do score minimo entram no resumo.
10. O app salva relatorios em `reports`.
11. O app envia e-mail com os melhores matches e sugestoes de curriculo.

## 12. Arquivos importantes

```text
JobMatcherApp.exe              Aplicativo desktop.
config/settings.py             Defaults seguros e leitura da config do usuario.
core/user_config.py            Salva e carrega configuracoes persistentes.
core/secure_store.py           Protege segredos com DPAPI no Windows.
core/cache.py                  Memoria local de vagas analisadas.
core/resume_parser.py          Le TXT e PDF.
core/matcher.py                Calcula match e sugestoes de curriculo.
notifier/email_notifier.py     Envia e-mails.
reports/                       Relatorios das varreduras.
```

## 13. Problemas comuns

Se o e-mail nao chega:

- confirme se a senha usada e senha de app, nao a senha normal do Gmail.
- confirme se a verificacao em duas etapas esta ativa.
- confira se o Gmail remetente esta correto.
- veja se o e-mail caiu em spam.

Se nao encontra vagas:

- confira a API key do Serper.
- tente termos de busca mais simples.
- reduza filtros muito especificos.
- rode uma `Varredura unica`.

Se o score parece errado:

- melhore o TXT de perfil.
- inclua projetos reais e tecnologias reais.
- confira se o curriculo PDF esta legivel.
- veja os gaps e as regras conservadoras no relatorio.
