# Push no Android com backend local

A implementação envia notificações visíveis pelo Expo Push Service/FCM quando o
app está em segundo plano ou fechado normalmente. Não exige que o JavaScript do
app fique consultando a API. Esta entrega habilita cadastro apenas no Android;
web continua com banners e iOS ainda precisa de configuração própria.

## 1. Firebase e Expo (uma vez)

- Crie ou use um projeto no https://console.firebase.google.com .
- Cadastre o app Android com o pacote **com.chargesense.tcc**.
- Baixe google-services.json e coloque em chargesense-mobile/google-services.json.
- Crie ou use um projeto em https://expo.dev e copie seu Project ID (UUID).
- No Firebase, Configurações do projeto > Contas de serviço > Gerar nova chave
  privada. Guarde esse JSON fora do repositório; não é o google-services.json.
- No painel Expo, abra o projeto > Settings > Credentials > Android, selecione
  com.chargesense.tcc e adicione a chave em FCM V1 service account key.
- Se a API FCM v1 estiver desativada no projeto Google, habilite-a.

Guia oficial: https://docs.expo.dev/push-notifications/fcm-credentials/
O backend não recebe a chave privada Firebase. Ele usa o token Expo do celular.

## 2. Reinstalar no celular USB

Na pasta chargesense-mobile, PowerShell:

```powershell
npm ci
$env:EXPO_PUBLIC_EAS_PROJECT_ID = "UUID_DO_PROJETO_EXPO"
$env:GOOGLE_SERVICES_JSON = "./google-services.json"
npx expo prebuild --platform android
npm run android
```

Mantenha as variáveis também no terminal que inicia o Metro. Só recarregar o JS
não instala os novos módulos nativos. Não use Expo Go para este teste.
Não é necessário emulador. Para testar sem Metro/USB, gere uma build release
com as mesmas variáveis (e assinatura apropriada); push não substitui a
configuração de distribuição do app.

## 3. Backend

Na pasta backend, instale novamente:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Use o mesmo terminal com as chaves e os limites já definidos. O computador
precisa ficar ligado, com backend e internet ativos. Se o Wokwi usa Cloudflare,
mantenha o túnel aberto. O backend faz conexões HTTPS de saída para exp.host.
Se habilitar segurança adicional do push no painel Expo, configure
CHARGESENSE_EXPO_ACCESS_TOKEN somente no terminal do backend.

## 4. Ativar e testar

1. Abra o app instalado e configure Backend local, endereço, chave de leitura e
   origem Simulador ou Sensores.
2. Em Ajustes, toque **Ativar notificações** e permita as notificações do Android.
3. Confira a estação, origem e servidor do registro salvo.
4. Envie valores normais, feche o app normalmente ou bloqueie a tela e provoque
   um agravamento com medições válidas. Para Wokwi, use measuredAt=null.
5. Espere a chegada da notificação na bandeja do Android; depois retorne ao normal.
6. Reduções intermediárias notificam dentro do app, mas não geram push; tensão e corrente são independentes.

Não use **Forçar parada** nas configurações do Android: o sistema pode impedir
notificações até o app ser aberto novamente. Restrições de bateria/rede e
permissões podem atrasar ou impedir entrega. Aceitação pela Expo/FCM não prova
que o usuário viu o aviso.

O registro permanece ao fechar o app, ao mudar abas ou entrar em demonstração.
Ao mudar endereço, origem ou chave, use **Atualizar registro de notificações**.
Para parar, use **Desativar notificações** com o backend acessível. A origem
assinada é exibida nos ajustes. Reinstalação ou rotação do token exige atualizar
o registro. Se o túnel antigo estiver indisponível ao trocar servidor, restaure
o acesso para remover a assinatura antiga ou remova-a administrativamente.

## Persistência e diagnóstico

SQLite recebe push_devices e push_jobs sem apagar dados. A criação do evento e
a fila são atômicas. Duplicatas da telemetria não duplicam jobs. Não há envio
retroativo para novos cadastros. Jobs pendentes sobrevivem a reinício e expiram
em 15 minutos; falhas temporárias têm tentativas com espera crescente. Tickets
são consultados após 15 minutos; tokens DeviceNotRegistered são removidos.
A fase done significa aceitação pelo provedor, não confirmação no celular.
Em timeout após aceitação, uma repetição do push ainda é possível.

Erros aparecem no terminal como Push job <id>: <tipo>. InvalidCredentials exige
revisar as credenciais Expo/FCM; HTTPStatusError pode exigir verificar o token
de acesso Expo. Para inspeção local:

```sql
SELECT id,event_id,phase,attempts,error FROM push_jobs ORDER BY id DESC LIMIT 20;
```

A chave de leitura permite cadastrar/desativar push (não publicar telemetria).
Tokens e o registro do app são guardados localmente; o app usa SecureStore.
Não há garantia de entrega de notificações para proteção elétrica.

## Diagnosticar ausência de push

Permissão Android não confirma cadastro no backend. Em Ajustes, use Ativar/Atualizar
registro. Depois toque Testar notificação em 15 segundos e vá para a tela inicial
do Android antes do envio. Com o app aberto, a apresentação de push é suprimida
para não duplicar banners internos.

Volte e toque Verificar entrega de notificações. O diagnóstico distingue registro
inexistente, worker parado, fila vazia, falha HTTP, ticket Expo e recibo FCM.
HTTP401: confira token de acesso Expo, se a segurança push estiver ativada.
InvalidCredentials: confira FCM V1 no Expo para com.chargesense.
MismatchSenderId: confira se o JSON do app e a chave FCM são do mesmo Firebase.
DeviceNotRegistered: atualize o registro. Ticket/recibo não comprovam exibição.
A consulta de recibos pode levar cerca de 15 minutos.

No emulador Android, use uma imagem com Google Play services e internet ativa.
Não use Forçar parada. O teste independe de Wokwi, limites e relógio de medição.
Endpoints POST push-test e push-diagnostics exigem chave de leitura e token do
próprio registro no corpo; nenhum token ou chave é retornado no diagnóstico.
