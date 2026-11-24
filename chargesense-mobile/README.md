# ChargeSense Mobile

Aplicativo Android do protótipo ChargeSense para monitoramento de uma estação de recarga. A interface possui quatro áreas: visão geral, histórico, eventos e configurações.

## Executar

Requisitos: Node.js 22, SDK Android e emulador ou celular Android com depuração USB.

```powershell
cd chargesense-mobile
npm ci
npm run typecheck
npm run android
```

## Modos de operação

- **Demonstração:** gera leituras fictícias localmente a cada 5 segundos. Não exige backend, internet, Wokwi ou ESP32. Os valores são explicitamente identificados como demonstração.
- **Backend local:** consulta a API FastAPI a cada 5 segundos, usando os endpoints `latest`, `status`, `readings` e `events` do contrato v1. Selecione a origem `simulated` ou `sensor` nas configurações.

A estação configurada nesta primeira entrega é `bancada-01`. A chave usada pelo aplicativo é exclusivamente a chave de leitura (`CHARGESENSE_READ_KEY`). **Nunca coloque `CHARGESENSE_DEVICE_KEY` no app.**

## Conectar ao backend local

1. Siga as instruções de execução em [backend/README.md](../backend/README.md).
2. Para emulador Android padrão, o endereço inicial é `http://10.0.2.2:8000`.
3. Para celular físico, inicie o Uvicorn com `--host 0.0.0.0`, descubra o IPv4 do computador na rede local e informe `http://IP_DO_PC:8000` no app.
4. Informe a mesma `CHARGESENSE_READ_KEY` criada no terminal que executa a API.
5. Escolha a origem dos dados. Para testar sem placa, execute `python tools/simulate.py` no diretório `backend`, com a chave de dispositivo definida no terminal.

O celular/emulador e o computador precisam conseguir se comunicar pela rede. Não use `localhost` no celular físico: esse endereço aponta para o próprio celular. Em redes corporativas ou de convidados, o tráfego entre dispositivos pode ser bloqueado.

## Segurança e limitações desta entrega

- A chave de leitura fica somente na memória do app enquanto ele está aberto; ainda não há armazenamento seguro ou login de usuários.
- A conexão HTTP sem TLS é destinada exclusivamente à bancada em rede local confiável. Não exponha a API à internet. Uma implantação real precisa de TLS, identidade por usuário/dispositivo e gestão segura de credenciais.
- Valores ausentes são exibidos como `—`, nunca convertidos em zero.
- Estado online indica recebimento recente pela API; não comprova que o veículo esteja carregando ou que um comando de corte tenha sido executado.
- O modo de demonstração é independente do backend. O histórico do backend é carregado da API; o modo local mantém o histórico apenas durante a sessão atual.
- Notificações push, autenticação de usuários e confirmação de atuação física não fazem parte desta primeira integração.

## Estrutura

- `src/App.tsx`: navegação e composição das telas.
- `src/types/telemetry.ts`: tipos alinhados ao contrato de telemetria.
- `src/services/api.ts`: cliente HTTP autenticado da API.
- `src/components/`: cartões de grandezas e estado de conexão.
- `src/theme/tokens.ts`: cores e espaçamentos da interface.
- `src/data/readings.ts`: persistência SQLite da implementação anterior, preservada para evolução do cache local.


## Avisos de tensão/corrente

No modo backend, eventos novos de limites geram um banner dentro do aplicativo,
com nível, origem, valor, limite, unidade e horário de recebimento. Funciona também
na interface web e não exige permissões de push. O botão Dispensar fecha o aviso;
a aba Eventos conserva o histórico. A primeira consulta apenas carrega histórico,
sem notificar retroativamente. Configure as regras seguindo backend/README.md.
Os banners exigem o app aberto. Para push com o Android fechado, consulte
[PUSH_SETUP.md](PUSH_SETUP.md). Não representa atuação ou confirmação de desligamento físico.

Cores de eventos e banners: atenção amarela, alerta laranja, crítico vermelho e
normalizado verde. Novos avisos ocorrem em agravamentos ou retorno ao normal;
reduções intermediárias são silenciosas. Eventos antigos permanecem no histórico.
