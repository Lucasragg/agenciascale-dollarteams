# Dollar Teams · Agência Scale

Dashboard de aquisição Meta Ads, publicada no GitHub Pages. Duas planilhas Google Sheets, com quatro abas, são lidas sem alteração pelo GitHub Actions. O site publica apenas agregados por data, campanha, conjunto e anúncio; não contém nomes, e-mails, IPs ou telefones dos inscritos. O cruzamento de e-mails acontece somente em memória durante o build.

## Fontes e regras

- Mídia: `MetaAds`, gid `2142085051`, da planilha `1YlmghmRdvXgjPaEppRH5fnyBxqADz70HalLv1jfAhMU`.
- Leads: `CurtoV3DP`, gid `1507896329`, da planilha `1XcaQNhwyzwpn8sW5gp9OgCRp0pVXyFceoXqVrmAP_3Q`.
- Investimento em USD, sem conversão, conforme confirmado pelo responsável.
- Uma linha com Registration date = uma inscrição/lead. Total Signups não é somado. Não se presume que inscrições sejam pessoas únicas.
- Free Trials e vendas vêm das abas `Impact` (gid `215288026`) e `Recuperacao` (gid `579566718`) na mesma planilha CurtoV3DP. `Event Type = Free Trial` conta como Free Trial; `Paid Trial` conta como venda. Contamos status Pending e Approved. Retenção e Full Price Shop não são inferidos como novas etapas de trial. Status Reversed, Declined e Rejected são excluídos; status desconhecidos impedem a publicação.
- `Sub Id 3` das duas abas é comparado a `Email` de CurtoV3DP usando trim e lowercase, sem remover pontos ou sufixos de e-mail. A atribuição herda as UTMs e preserva a data da ação. E-mails sem correspondência ou com múltiplas origens distintas ficam sem atribuição paga. Repetições de inscrições com a mesma origem não multiplicam ações nem contatos da coorte.
- As quatro abas são relidas a cada build; o snapshot antigo `data/impact.json` é um arquivo histórico agregado usado somente no modo local legado, não é somado aos dados atuais. E-mails e Action IDs não são persistidos em arquivos, logs ou artefatos públicos do build na nuvem.
- Conversão lead → Free Trial = contatos por e-mail inscritos no período que tiveram trial / contatos inscritos no período. Conversão Free Trial → venda = contatos desse grupo com trial seguido de Paid Trial / contatos com trial. A observação vai até a menor data final entre as duas abas de conversão; grupos recentes ainda estão em maturação. As taxas usam contatos, enquanto os cards de volume contam ações distintas. A base de contatos é recalculada em cada atualização.
- Eventos anteriores à data de inscrição ficam nas contagens com sinalização de revisão e são excluídos das taxas de avanço. A ordem de horários do mesmo dia permanece provisória enquanto os fusos não forem confirmados. Um e-mail não equivale necessariamente a uma loja; a atribuição é provisória.
- Custo por Free Trial = investimento do período / ações Free Trial atribuídas no período. Exibido em USD nos cards, tabelas, gráfico e exportação CSV; sem Free Trials ou sem cobertura, aparece como “—”.
- CAC = investimento do período / ações Paid Trial atribuídas no período. Taxas, CFT e CAC requerem cobertura comum das duas abas de conversão, além das fontes de mídia/leads quando aplicável. As datas mínima/máxima de cada aba são informadas na interface; dias fora da cobertura não são tratados como zero.
- Action IDs na planilha podem colidir entre pessoas e horários diferentes. A identidade usada para remover repetições é Action Id + data/hora + marca + tipo de evento + e-mail normalizado, dentro e entre abas. IDs iguais com identidades diferentes são preservados; mesmo e-mail com Action IDs distintos não é deduplicado. Status conflitantes para a mesma identidade impedem a publicação. Diagnósticos agregados indicam repetições removidas, IDs colidentes, eventos excluídos, correspondência por e-mail e atribuição paga.
- Faturamento = soma de `Action Earnings` de todos os tipos de evento com status Pending ou Approved nas duas abas, incluindo Full Price Shop e retenção se houver comissão. Trata-se de comissões, incluindo pendências, não de caixa recebido. A escala foi confirmada pelo responsável: o valor armazenado `1.450.000` equivale a US$ 145,00; portanto dividimos as unidades da planilha por 10.000. O processamento usa Decimal e armazena centavos inteiros. Valores inválidos, frações de centavo incompatíveis com essa escala ou comissões conflitantes em eventos duplicados impedem a publicação.
- O card Faturamento é o último da grade. Sem filtros de mídia, soma todas as comissões do período, inclusive as sem correspondência de e-mail/UTM. Com campanha, conjunto ou anúncio filtrado, soma apenas as comissões atribuídas ao filtro. A data é a da ação. A comparação com o período anterior requer cobertura das duas abas de comissões; períodos parcialmente cobertos mostram o total conhecido com indicação da base disponível. Seleções das caixas de comparação dos gráficos continuam independentes dos filtros globais e não mudam o card.
- UTM campaign → Campaign ID, UTM term → Ad Set ID, UTM content → Ad ID. Prioridade: anúncio, conjunto, campanha. Fallback por nome exato e único no contexto da campanha. IDs são preservados como strings. IDs conflitantes ficam sem atribuição.
- A leitura de leads usa exportação CSV nativa, preservando colunas de UTM com IDs numéricos e nomes antigos misturados. A consulta GViz removia silenciosamente valores de texto dessas colunas. E-mail, data e UTMs são lidos no mesmo snapshot de E:AG; apenas essas sete colunas são retidas em memória. Campos intermediários são descartados imediatamente. As abas de conversões usam A:K e retêm os seis campos de identificação/atribuição e Action Earnings.
- Leads sem UTM ou sem correspondência são exibidos separadamente, sem classificá-los automaticamente como orgânicos. Não entram no CPL pago nem na conversão paga. Atribuição parcial é conservada e aparece em linhas próprias nas tabelas.
- IDs são cruzados contra todo o histórico da mídia. O resultado é agregado na data da inscrição, sem exigir que o anúncio tenha gasto nesse dia.
- Datas seguem o dia exibido na fonte. O webinar não inclui fuso nos horários exportados; nenhuma conversão de fuso é presumida. Hoje usa America/Sao_Paulo na interface.
- O período anterior tem o mesmo tamanho, imediatamente antes do selecionado. Variações só aparecem quando ambas as fontes cobrem os dois períodos. Hoje é parcial. A cobertura é inferida pelas datas extremas das fontes, não certifica integridade de cada dia.
- A base de webinar começa depois da mídia e cobre CurtoV3DP; o gasto inclui todas as campanhas da MetaAds. O filtro de campanha permite delimitar a análise. Leads de outros formulários/webinars não presentes nessa fonte não são inferidos.
- CPM = gasto / impressões × 1000; CTR = cliques no link / impressões; CPC = gasto / cliques; CPL = gasto / leads pagos; conversão clique → lead = leads pagos / cliques; conversão LP → lead = leads pagos / page views; connect rate = page views / cliques. Divisões por zero aparecem como “—”.
- Linhas de mídia idênticas (mesma data, IDs e métricas) são deduplicadas. O indicador Leads continua contando inscrições; os e-mails são usados apenas para atribuição das conversões e taxas por contatos.

## Automação na nuvem

`.github/workflows/deploy.yml` executa a cada hora, no minuto 17 UTC (também minuto 17 em Brasília), em push e sob acionamento manual. O agendador do GitHub pode atrasar execuções. Um pequeno commit mensal de atividade mantém o repositório público ativo, evitando a suspensão do agendamento por 60 dias sem atividade. Tudo roda em runners do GitHub, sem agendador ou serviço no computador do usuário.

1. Executa testes de atribuição.
2. Lê as quatro abas públicas com retentativas e cache-bust, retendo apenas os campos necessários.
3. Valida esquema, datas, IDs e números. Em falha, não publica um snapshot incompleto.
4. Cruza e-mails em memória, agrega conversões e gera `dist/data.json`, sem dados pessoais. Se qualquer aba falhar, preserva a versão publicada anterior.
5. Publica `dist` como artifact do GitHub Pages usando `GITHUB_TOKEN` efêmero. Nenhum PAT é necessário à rotina.

O navegador consulta atualizações a cada 5 minutos e ao voltar à aba, usando `cache: no-store` e query string única. CSS/JS recebem versão pelo hash do conteúdo. Uma versão válida permanece visível se a próxima atualização falhar. A página informa data/hora de leitura e alerta se a publicação tiver mais de duas horas.

As fontes precisam continuar acessíveis por link. A atualização do dashboard não atualiza o conector que alimenta as planilhas.

## Desenvolvimento

A tabela de detalhamento diário fica imediatamente abaixo dos cards, em ordem decrescente de data, com todas as 17 métricas dos cards e conversão clique → lead. Os cabeçalhos permitem selecionar múltiplas séries no gráfico de evolução logo abaixo. O gráfico inicia vazio; a seleção permanece ao alterar período/campanha/conjunto/anúncio. Uma métrica usa valores reais no eixo Y; múltiplas métricas usam escala relativa por série (100% = pico da métrica no período), com valores reais no tooltip. Dados indisponíveis ficam como lacunas. Os cabeçalhos funcionam por teclado, e as setas no gráfico permitem consultar datas.

Os 18 cards compactos seguem a ordem do funil: Investimento, Impressões, Cliques, CPM, CTR, CPC, Landing page views, Connect rate, Leads, Custo por lead, Free Trials, Custo por Free Trial, Paid Trial, Custo por Paid Trial, Conversão página → lead, Conversão lead → Free Trial, Conversão Free Trial → Paid e Faturamento. O custo por Paid Trial usa o mesmo cálculo de CAC. Cada card inclui uma descrição curta e comparação com o período anterior. Em desktop amplo são seis cards por linha; a grade se adapta a telas menores.

A Decisão de mídia tem três tabelas simultâneas: campanhas, conjuntos e anúncios. Cada tabela tem rolagem vertical limitada a 425 px (360 px no celular), cabeçalho e primeira coluna fixos, busca, ordenação e exportação CSV independentes. Clicar no nome de uma entidade aplica seu filtro à dashboard; o caminho acima das tabelas permite voltar aos níveis anteriores ou limpar os filtros.

Cada tabela possui seu próprio gráfico de evolução, inicialmente vazio. Clicar no nome de um cabeçalho adiciona ou remove uma métrica; o botão de seta ao lado ordena a coluna. As seleções de métricas são independentes e persistem ao alterar período ou filtros. O gráfico agrega por dia somente os registros das linhas que correspondem à busca e aos filtros daquela tabela, preservando atribuições parciais. Custos e taxas usam razões entre totais, nunca médias de razões. O comportamento de escala, tooltip, lacunas e teclado é o mesmo do gráfico de detalhamento diário. Busca sem resultados mostra um estado vazio, sem inventar uma série de zeros.

As caixas ao lado dos nomes permitem selecionar múltiplas campanhas, conjuntos ou anúncios para comparação no gráfico daquela tabela. Com itens selecionados, cada combinação de item e métrica tem uma série própria, identificada por nome e ID; a cor identifica o item, e os traços diferenciam as métricas. Uma única métrica compara todos os itens na mesma escala real. Com várias métricas, cada métrica usa um máximo compartilhado entre todos os itens, preservando a diferença de desempenho entre eles. Os valores reais aparecem no tooltip. Se nenhuma métrica estava selecionada, marcar um item inicia a comparação por CPL.

A seleção de itens é independente em cada tabela e acompanha as mudanças de período e filtros globais, sem alterar os cards nem aplicar um filtro global por si só. A busca permite localizar e adicionar novos itens sem remover os anteriores do gráfico. Itens fora do período ou dos filtros globais permanecem selecionados, mas ficam fora das séries, com aviso da quantidade. “Selecionar visíveis” adiciona as linhas da busca; “Limpar itens” retorna ao gráfico agregado da busca e dos filtros atuais, mantendo as métricas escolhidas. As seleções permanecem durante as atualizações automáticas na mesma página.

O gráfico **Eficiência · CPL, CFT e CAC por dia**, após as três tabelas, acompanha o período e a seleção de campanha, conjunto ou anúncio. Exibe três séries na mesma escala monetária em US$: CPL = investimento ÷ leads; CFT = investimento ÷ Free Trials; CAC = investimento ÷ Paid Trials. O eixo X mostra datas. O tooltip informa os três custos, investimento e volumes do dia. Cada série fica com lacunas quando falta cobertura ou seu denominador é zero. As seleções dos gráficos de evolução são independentes deste gráfico fixo de custos.

Python 3.12 ou superior; apenas biblioteca padrão.

```sh
python -m unittest discover -s tests -v
python scripts/build_data.py
python -m http.server 8766 -d dist
```

O diretório `public` contém os fontes; `dist` é gerado. Não publique planilhas brutas ou credenciais.

Para auditoria histórica local de um CSV (não utilizado pelo build de produção):

```sh
python scripts/impact_data.py caminho/impact.csv --leads .local/impact-lead-match-source.json --ads .local/ads.json --output data/impact.json
python -m unittest discover -s tests -v
python scripts/build_data.py
```

O importador legado verifica vazamento de e-mails e rejeita Action IDs repetidos. O build na nuvem usa `scripts/live_trials.py` para ler as novas abas, tratar colisões de IDs e preparar um novo agregado completo em cada execução.
