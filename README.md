# Dollar Teams · Agência Scale

Dashboard de aquisição Meta Ads, publicada no GitHub Pages. Duas fontes Google Sheets são lidas sem alteração, pelo GitHub Actions. O site publica apenas agregados por data, campanha, conjunto e anúncio; não contém nomes, e-mails, IPs ou telefones dos inscritos.

## Fontes e regras

- Mídia: `MetaAds`, gid `2142085051`, da planilha `1YlmghmRdvXgjPaEppRH5fnyBxqADz70HalLv1jfAhMU`.
- Leads: `CurtoV3DP`, gid `1507896329`, da planilha `1XcaQNhwyzwpn8sW5gp9OgCRp0pVXyFceoXqVrmAP_3Q`.
- Investimento em USD, sem conversão, conforme confirmado pelo responsável.
- Uma linha com Registration date = uma inscrição/lead. Total Signups não é somado. Não se presume que inscrições sejam pessoas únicas.
- Free Trials e vendas vêm do CSV da Impact de 16/09/2026; vendas = ações Paid Trial, com status Pending nessa exportação. A atribuição por e-mail herda as UTMs da inscrição e preserva a data da ação, mesmo quando ocorre dias depois. São 673 Free Trials e 182 Paid Trials com origem de mídia identificada no histórico importado.
- `data/impact.json` contém apenas o snapshot agregado. O arquivo bruto e os e-mails ficam fora da publicação. Atualizações horárias de mídia e leads preservam esse snapshot; Impact ainda não está conectado à API.
- Conversão lead → Free Trial = contatos por e-mail inscritos no período que tiveram trial / contatos inscritos no período. Conversão Free Trial → venda = contatos desse grupo com trial seguido de Paid Trial / contatos com trial. A observação vai até a data do CSV; grupos recentes ainda estão em maturação. As taxas usam contatos, enquanto os cards de volume contam ações distintas. A base de contatos acompanha o snapshot da importação.
- Eventos anteriores à data de inscrição ficam nas contagens com sinalização de revisão e são excluídos das taxas de avanço. A ordem de horários do mesmo dia permanece provisória enquanto os fusos não forem confirmados. Um e-mail não equivale necessariamente a uma loja; a atribuição é provisória.
- Custo por Free Trial = investimento do período / ações Free Trial atribuídas no período. Exibido em USD nos cards, tabelas, gráfico e exportação CSV; sem Free Trials ou sem cobertura, aparece como “—”.
- CAC = investimento do período / ações Paid Trial atribuídas no período. Taxas e CAC não são mostrados para períodos que ultrapassam a data do snapshot; dias sem importação não são tratados como zero. Cada atualização manual deve regenerar o snapshot completo, sem anexar duplicatas.
- UTM campaign → Campaign ID, UTM term → Ad Set ID, UTM content → Ad ID. Prioridade: anúncio, conjunto, campanha. Fallback por nome exato e único no contexto da campanha. IDs são preservados como strings. IDs conflitantes ficam sem atribuição.
- A leitura de leads usa exportação CSV nativa, preservando colunas de UTM com IDs numéricos e nomes antigos misturados. A consulta GViz removia silenciosamente valores de texto dessas colunas. Datas e UTMs são lidas em um único snapshot do intervalo J:AG; somente as seis colunas necessárias são retidas, e as intermediárias são descartadas em memória.
- Leads sem UTM ou sem correspondência são exibidos separadamente, sem classificá-los automaticamente como orgânicos. Não entram no CPL pago nem na conversão paga. Atribuição parcial é conservada e aparece em linhas próprias nas tabelas.
- IDs são cruzados contra todo o histórico da mídia. O resultado é agregado na data da inscrição, sem exigir que o anúncio tenha gasto nesse dia.
- Datas seguem o dia exibido na fonte. O webinar não inclui fuso nos horários exportados; nenhuma conversão de fuso é presumida. Hoje usa America/Sao_Paulo na interface.
- O período anterior tem o mesmo tamanho, imediatamente antes do selecionado. Variações só aparecem quando ambas as fontes cobrem os dois períodos. Hoje é parcial. A cobertura é inferida pelas datas extremas das fontes, não certifica integridade de cada dia.
- A base de webinar começa depois da mídia e cobre CurtoV3DP; o gasto inclui todas as campanhas da MetaAds. O filtro de campanha permite delimitar a análise. Leads de outros formulários/webinars não presentes nessa fonte não são inferidos.
- CPM = gasto / impressões × 1000; CTR = cliques no link / impressões; CPC = gasto / cliques; CPL = gasto / leads pagos; conversão clique → lead = leads pagos / cliques; conversão LP → lead = leads pagos / page views; connect rate = page views / cliques. Divisões por zero aparecem como “—”.
- Linhas de mídia idênticas (mesma data, IDs e métricas) são deduplicadas. Inscrições não são deduplicadas por dados pessoais; eles sequer são consultados pelo build.

## Automação na nuvem

`.github/workflows/deploy.yml` executa a cada hora, no minuto 17 UTC (também minuto 17 em Brasília), em push e sob acionamento manual. O agendador do GitHub pode atrasar execuções. Um pequeno commit mensal de atividade mantém o repositório público ativo, evitando a suspensão do agendamento por 60 dias sem atividade. Tudo roda em runners do GitHub, sem agendador ou serviço no computador do usuário.

1. Executa testes de atribuição.
2. Lê somente as colunas necessárias das duas fontes públicas, com retentativas e cache-bust.
3. Valida esquema, datas, IDs e números. Em falha, não publica um snapshot incompleto.
4. Gera `dist/data.json`, sem dados pessoais.
5. Publica `dist` como artifact do GitHub Pages usando `GITHUB_TOKEN` efêmero. Nenhum PAT é necessário à rotina.

O navegador consulta atualizações a cada 5 minutos e ao voltar à aba, usando `cache: no-store` e query string única. CSS/JS recebem versão pelo hash do conteúdo. Uma versão válida permanece visível se a próxima atualização falhar. A página informa data/hora de leitura e alerta se a publicação tiver mais de duas horas.

As fontes precisam continuar acessíveis por link. A atualização do dashboard não atualiza o conector que alimenta as planilhas.

## Desenvolvimento

Os 17 cards compactos seguem a ordem do funil: Investimento, Impressões, Cliques, CPM, CTR, CPC, Landing page views, Connect rate, Leads, Custo por lead, Free Trials, Custo por Free Trial, Paid Trial, Custo por Paid Trial, Conversão página → lead, Conversão lead → Free Trial e Conversão Free Trial → Paid. O custo por Paid Trial usa o mesmo cálculo de CAC. Cada card inclui uma descrição curta e comparação com o período anterior. Em desktop amplo são seis cards por linha; a grade se adapta a telas menores.

O gráfico **Eficiência · CPL por dia**, abaixo da tabela de Decisão de mídia, acompanha o período e a seleção de campanha, conjunto ou anúncio. O eixo X mostra datas e o eixo Y mostra CPL em US$. O tooltip informa CPL, investimento e leads daquele dia, com comparação ao período anterior. Dias sem leads ou sem cobertura não são desenhados como CPL zero.

Python 3.12 ou superior; apenas biblioteca padrão.

```sh
python -m unittest discover -s tests -v
python scripts/build_data.py
python -m http.server 8766 -d dist
```

O diretório `public` contém os fontes; `dist` é gerado. Não publique planilhas brutas ou credenciais.

Para importar um novo CSV local com uma leitura atualizada de e-mails, datas e UTMs dos leads:

```sh
python scripts/impact_data.py caminho/impact.csv --leads .local/impact-lead-match-source.json --ads .local/ads.json --output data/impact.json
python -m unittest discover -s tests -v
python scripts/build_data.py
```

O importador publica somente campos agregados permitidos, verifica vazamento de e-mails e rejeita Action IDs repetidos. A rotina de nuvem não lê e-mails: apenas combina o snapshot agregado com as fontes já utilizadas pela dashboard.
