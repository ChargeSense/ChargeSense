# Protótipo de aquisição elétrica — TCC Kaiki

Versão para o repositório: 16/11/2026. Base: Lista_bancada_ESP32(1).xlsx, abas Lista de compras, Resistores e Compatibilidade. Escopo: um circuito AC representando uma estação, inicialmente com carga resistiva. Não é medidor certificado nem dispositivo de proteção. Não representa medição DC da bateria ou comunicação com o veículo.

## 1. Premissas que precisam ser confirmadas

- Placa ESP32 clássica WROOM/DevKit. Código em C para ESP-IDF 5.2.5; outros ESP32 exigem adaptação.
- Sensor de corrente preferido na planilha: SCT-013-005, saída 1 V RMS a 5 A RMS. Confirmar etiqueta e pinagem. A lista não prova posse de cada item.
- Fonte informada pelo grupo: AC ajustável de 10 a 30 V. Modelo, frequência, isolamento e corrente máxima ainda desconhecidos. ZMPT e SCT não medem DC estacionária. Uma fonte DC de bancada não serve como fonte do ensaio com estes sensores.
- Preferir ensaio inicial com fonte AC isolada de baixa tensão, por exemplo 12–24 V AC, dentro da capacidade do laboratório. A isolação da fonte disponível ainda NÃO foi confirmada. Testar a sensibilidade do ZMPT nessa faixa; ela pode ser insuficiente. Não aumentar a tensão só para obter leitura.
- Carga, condutores, fusível, corte manual e montagem de potência precisam de dimensionamento pelo laboratório. Exemplo apenas de cálculo: 12 V / 24 ohms = 0,5 A e 6 W; a potência nominal e dissipação do resistor devem seguir a curva térmica do fabricante. Resistores de 1/4 W da lista não são cargas de potência.

## 2. Estrutura elétrica

Fonte AC isolada → proteção/corte manual → carga. O SCT abraça APENAS UM condutor isolado da carga; não abraçar ida e retorno juntos. O ZMPT mede em paralelo com os terminais da carga. Instalar tudo desenergizado. Em etapa futura, colocar o elemento de corte antes da carga e do ponto de medição de tensão; manter a eletrônica alimentada separadamente para observar o pós-corte.

Protoboard apenas para sinais isolados e alimentação da eletrônica. Não levar rede 127/220 V, resistores quentes ou corrente de potência ao protoboard. A parte primária do ZMPT é circuito de potência; a isolação do componente não torna qualquer placa/montagem segura para rede. Ensaios em rede exigem responsável habilitado, proteções, invólucro e instrumentos adequados. Nunca ligar neutro/fase ao GND do ESP32.

### Canal de tensão

1. Alimentar o módulo ZMPT conforme a especificação da placa efetivamente comprada (frequentemente 5 V; confirmar). GND do lado de saída unido ao GND do ESP32.
2. OUT do módulo → resistor 10 kΩ → nó V_ADC. Nó V_ADC → resistor 10 kΩ → GND.
3. V_ADC → GPIO34 / ADC1_CH6. O divisor divide o sinal completo, inclusive o offset DC, por 2. Não se aplica à entrada de potência do ZMPT.
4. Antes de conectar ao GPIO, verificar no osciloscópio o sinal na maior tensão de ensaio. Ajustar o ganho do módulo para não recortar internamente nem exceder a faixa útil do ADC. Faixa de trabalho inicial conservadora: aproximadamente 0,3–2,4 V instantâneos, a confirmar na placa. Não basta estar abaixo de 3,3 V.

### Canal de corrente — SCT com saída 1 V

A polarização sozinha, como proposta preliminar da planilha, leva 1 V RMS a 1,65 ± 1,414 V, aproximadamente 0,236–3,064 V. Isso deixa pouca margem e pode sair da faixa de boa exatidão do ADC clássico. Usar atenuação adicional no ensaio de faixa completa:

1. 3V3 → 10 kΩ → VBIAS → 10 kΩ → GND. VBIAS ≈ 1,65 V.
2. Capacitor 10 µF de VBIAS (positivo) para GND (negativo); 100 nF em paralelo junto ao nó.
3. Um terminal do SCT → VBIAS. Outro terminal → 10 kΩ → nó I_ADC.
4. Nó I_ADC → 10 kΩ → VBIAS. I_ADC → GPIO35 / ADC1_CH7.
5. Assim, aproximadamente I_ADC = 1,65 V + 0,5 × v_SCT. A 5 A senoidais no SCT-005: cerca de 0,943–2,357 V. É cálculo nominal, não validação de circuito. Corrente com picos elevados pode sair dessa faixa mesmo com RMS abaixo de 5 A.

Isso requer dois resistores adicionais de 10 kΩ. Podem ser os dois de reserva da planilha nesta etapa; para conservar a reserva, adquirir mais dois. Atenuação não é burden: o SCT de saída 1 V já possui carga interna. Não instalar o resistor de 18 Ω reservado ao SCT-013-000. Não usar a variante 000 neste circuito sem reprojetar o burden; secundário de TC com saída de corrente não deve ser aberto durante a medição.

Conferir terminal comum/pinagem do jack com o sensor real. GND, VBIAS e sinal são nós diferentes. Desacoplar a alimentação do módulo com os demais 100 nF. Não adicionar arbitrariamente 100 nF entre ADC e GND: a impedância do divisor forma um filtro e altera amplitude/fase. O condicionamento proposto ainda precisa de avaliação de impedância, ruído e eventual buffer/filtro antialias antes de cargas com chaveamento.

## 3. O que o firmware faz

ADC1 em DMA, padrão alternado GPIO34/GPIO35, taxa solicitada de 20.000 conversões/s no total (10.000 por canal). Não são amostras simultâneas: há aproximadamente 50 µs entre canais. Um buffer com atraso de 32 pares permite interpolar tensão para o instante da corrente. SENSOR_PHASE_SAMPLES adiciona ajuste de fase dos sensores. O ajuste é limitado a ±20 períodos de 100 µs; não supor que fase seja constante em toda a faixa.

Janelas contínuas de 10.000 pares produzem aproximadamente uma linha CSV por segundo. A cada janela remove-se a média DC e calcula-se:

- Vrms = KV × sqrt(média((v − média(v))²)).
- Irms = KI × sqrt(média((i − média(i))²)).
- S = Vrms × Irms, em VA.
- P estimada = KV × KI × média((v − média(v))(i − média(i))), em W.
- FP estimado = P/S, com sinal. Não transformar P negativo em positivo para esconder inversão do sensor.
- Energia líquida = soma(P × duração/3600), em Wh, somente com POWER_VALIDATED=1 e janelas aceitas.

Os ganhos convertem contagens diretamente para V/A do circuito medido e incluem toda a cadeia. Não se assume ADC ideal de 3,3/4095. Isso exige calibração externa em vários pontos; uma constante não elimina a não linearidade do ADC. Interpolação também altera a resposta em frequências elevadas. Janela fixa não é sincronizada à rede: se a frequência variar, podem surgir erros de borda.

O programa exporta RMS em contagens, offsets, mínimos/máximos digitais, Vrms, Irms, S, P/FP estimados, energia e estado. Antes dos ganhos, unidades físicas aparecem como nan. P/FP permanecem marcados como não validados por padrão. Energia também permanece nan. Após habilitada, energia é apenas a soma das janelas válidas da sessão, com tempo nominal; não preenche lacunas, não persiste após reinício e pode diminuir com P negativa. Janela inválida mantém acumulado anterior e status de falha: não significa consumo zero. O tempo CSV é nominal de amostras processadas, não horário civil.

Overflow, timeout ou sequência inesperada interrompem a coleta até reinício; não se integra dados após perda silenciosa. O diagnóstico de recorte é grosseiro: não detecta toda saturação do sensor ou do amplificador. Sinal baixo pode ser ausência real de carga OU falha/desconexão; não serve para confirmar abertura de contato. Sem sensor de referência adicional não se distingue todos esses casos.

DS18B20, relé, botão, LEDs e Wi-Fi ficam para a próxima etapa; este firmware não configura nem aciona esses GPIOs. Deixar o relé desconectado nesta fase. Temperatura não é grandeza elétrica e acrescentá-la agora não valida a aquisição. Futuro corte de circuito real precisa de contator/proteções dimensionados, não do pequeno relé experimental como única proteção.

## 4. Compilar e gravar

Instalar ESP-IDF 5.2.5 pelo ambiente oficial Espressif. Abrir o terminal ESP-IDF na pasta que contém o CMakeLists.txt principal:

```sh
idf.py set-target esp32
idf.py build
idf.py -p COM5 flash monitor
```

Substituir COM5 pela porta real; em Linux pode ser /dev/ttyUSB0. Monitor serial padrão: 115200 baud. Sair do monitor com Ctrl+]. Arquivo principal: main/main.c. Ajustes: main/config.h. Este projeto usa C nativo (app_main), não é sketch Arduino .ino.

Para registrar o ensaio, habilitar o log do monitor ESP-IDF (Ctrl+T, Ctrl+L). O log contém mensagens de inicialização; conservar a linha de cabeçalho CSV e as linhas de dados, excluindo logs iniciados em # e mensagens do sistema antes de importar. Separador vírgula, decimal ponto. Não enviar cada amostra ao terminal durante DMA: isso pode causar perda de dados.

## 5. Calibração passo a passo

1. Confirmar fonte AC, isolamento, placa e etiqueta do SCT. Medir GND, VBIAS e alimentação sem carga energizada.
2. Validar mínimo, máximo e forma de onda nos dois pinos com osciloscópio, do menor ao maior patamar de ensaio, antes de conectá-los ao ESP32. Não usar a bancada próxima à saturação. A taxa solicitada também precisa ser verificada na placa.
3. Deixar os ganhos zero e registrar o ruído em repouso. MIN_RMS_COUNTS=3 é apenas limiar inicial; ajustar com evidência. Não zerar arbitrariamente correntes pequenas.
4. Aplicar sinal AC e carga resistiva estável de referência. Calcular KV = tensão RMS de referência / vr_counts. Calcular KI = corrente RMS de referência / ir_counts. Não usar offsets ou mínimos/máximos nesse cálculo. Exemplo hipotético: 12,00 V / 120,00 contagens = 0,10000 V/contagem; 0,500 A / 80,00 = 0,00625 A/contagem. Estes NÃO são ganhos do equipamento de vocês.
5. Inserir ganhos em VOLTS_PER_COUNT e AMPS_PER_COUNT, recompilar/gravar. Validar pelo menos três patamares diferentes; registrar referência, medida, erro absoluto, erro relativo e dispersão. Perto de zero, preferir erro absoluto. Se o erro variar muito pela faixa, reduzir faixa/ruído ou rever ADC/condicionamento; não apenas reajustar o ganho.
6. Comparar P/FP com analisador de potência, primeiro com carga resistiva, depois com carga reativa/não linear. Corrigir polaridade (CURRENT_SIGN ou orientação do SCT). Ajustar SENSOR_PHASE_SAMPLES usando referência de fase/onda e potência, não apenas forçando FP=1. Se a corrente atrasa a tensão por erro dos sensores, em geral é necessário atrasar a tensão, isto é, ajuste negativo; confirmar experimentalmente. Recalibrar KV após mudar interpolação.
7. Somente após ganho, fase e taxa aprovados, habilitar POWER_VALIDATED. Comparar energia num intervalo conhecido com instrumento de referência. Não confiar em ensaio resistivo único para alegar exatidão em carregador VE.

Definir previamente com o orientador os critérios de aceitação, corrente mínima confiável, faixa de tensão e erro permitido. Não há promessa de precisão metrológica neste projeto inicial. Um carregador é carga eletrônica: corrente não senoidal e interferências podem exigir filtro, buffer ou medidor dedicado na evolução do TCC.

## 6. Verificações realizadas e pendentes

Teste numérico em C do mesmo módulo measurement.c: senoides com offsets, RMS, fase de 0/60/180 graus, três janelas contínuas, sinal constante e recorte. Rodar no computador:

```sh
gcc -std=c11 -Wall -Wextra -Werror -I main main/measurement.c tests/test_measurement.c -lm -o /tmp/test_measurement
/tmp/test_measurement
```

A compilação ESP-IDF é verificada pela workflow `ESP32 firmware` do repositório; consultar o resultado da execução do commit em uso. Não houve gravação ou validação elétrica em placa. O teste numérico não valida DMA, taxa real, pinagem, ganho, ruído, segurança ou exatidão dos sensores. A etapa de bancada é obrigatória antes de usar resultados no TCC.

## 7. Referências técnicas

- Espressif, ESP-IDF 5.2, ADC contínuo: https://docs.espressif.com/projects/esp-idf/en/v5.2/esp32/api-reference/peripherals/adc_continuous.html
- Espressif, calibração ADC: https://docs.espressif.com/projects/esp-idf/en/v5.2/esp32/api-reference/peripherals/adc_calibration.html
- OpenEnergyMonitor, interface de TC: https://docs.openenergymonitor.org/electricity-monitoring/ct-sensors/interface-with-arduino.html
- OpenEnergyMonitor, calibração: https://docs.openenergymonitor.org/electricity-monitoring/ctac/calibration.html
- Características/modelos de compra: planilha fornecida; confirmar datasheet e etiqueta do produto recebido. Página do fabricante YHDC não respondeu durante esta consulta.
