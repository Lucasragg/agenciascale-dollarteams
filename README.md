# Dollar Teams · Agência Scale

Dashboard de aquisição Meta Ads, publicada no GitHub Pages. Duas fontes Google Sheets são lidas sem alteração, pelo GitHub Actions. O site publica apenas agregados por data, campanha, conjunto e anúncio; não contém nomes, e-mails, IPs ou telefones dos inscritos.

## Fontes e regras

- Mídia: `MetaAds`, gid `2142085051`, da planilha `1YlmghmRdvXgjPaEppRH5fnyBxqADz70HalLv1jfAhMU`.
- Leads: `CurtoV3DP`, gid `1507896329`, da planilha `1XcaQNhwyzwpn8sW5gp9OgCRp0pVXyFceoXqVrmAP_3Q`.
- Investimento em USD, sem conversão, conforme confirmado pelo responsável.
- Uma linha com Registration date = uma inscrição/lead. Total Signups não é somado. Não se presume que inscrições sejam pessoas únicas. Vendas foram excluídas por solicitação do responsável.
- UTM campaign → Campaign ID, UTM term → Ad Set ID, UTM content → Ad ID. Prioridade: anúncio, conjunto, campanha. Fallback por nome exato e único no contexto da campanha. IDs são preservados como strings. IDs conflitantes ficam sem atribuição.
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

Python 3.12 ou superior; apenas biblioteca padrão.

```sh
python -m unittest discover -s tests -v
python scripts/build_data.py
python -m http.server 8766 -d dist
```

O diretório `public` contém os fontes; `dist` é gerado. Não publique planilhas brutas ou credenciais.
