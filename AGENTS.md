#Instruções Iniciais

Estamos desenvolvendo um leitor de logs ETL do Elipse E3 para monitoramento operacional e futura alimentação de um modelo de machine learning.

Arquivos de referência anexados:
- main.vbs: código-fonte atual e funcional.
- ONREAD_OUTPUTS.md: descrição resumida das saídas OnRead_.
- Arquivo .etl de exemplo, se anexado: referência para validar marcadores e campos reais.

Contexto atual:
- O script roda no ambiente de scripts do Elipse E3, em VBScript.
- Versão atual do código: 1.7 (2026-07-12).
- O leitor localiza o ETL mais recente por pasta e prefixo configuráveis.
- Para reduzir carga em produção, lê apenas o trecho final do ETL (tail de 1 MB), onde ficam os registros mais recentes.
- Não usa WMI, tracerpt, executáveis externos, arquivos temporários ou saída em TXT.
- Não coletamos dados externos do Windows; somente informações presentes no ETL.
- O objetivo é manter o script muito leve, estável e adequado a execução recorrente em produção.

O código expõe 48 saídas OnRead_, incluindo:
- Métricas do E3Run: CPU, PVT, HDL, threads, uptime, occupancy, tempo médio de scripts, erros/minuto, memória e page faults.
- Eventos Local/Remote: pendentes, taxas de queued/handled/discarded, crescimento de fila e percentual de descarte.
- Métricas de processo/resumo: CPU global, threads globais, espaço livre em C:, fila de E/S, E3Server.
- Controle de qualidade: ETL alterado, registros encontrados, idade da amostra, reset de contadores, status e tempo total de execução.

Regras importantes:
1. Antes de sugerir alterações, leia o main.vbs inteiro e considere-o como fonte de verdade.
2. Preserve compatibilidade com o ambiente VBScript do Elipse E3.
3. Não introduza dependências externas, WMI, executáveis, banco de dados, arquivos temporários ou leituras completas do ETL sem justificar claramente o impacto.
4. Priorize desempenho, previsibilidade e tolerância a campos ausentes.
5. Nenhum campo ausente no ETL pode causar quebra do script.
6. Deltas e taxas devem sempre usar a estampa de tempo dos registros do ETL, nunca o horário da leitura.
7. O ID numérico no início de cada linha ETL pode ser futuramente usado para continuidade da sequência, mas não altere o código por essa razão sem solicitação explícita.
8. Não altere o código a menos que eu peça explicitamente; em dúvidas, responda objetivamente com base no fonte atual.
9. Quando alterar o código, incremente a versão e registre no cabeçalho comentários objetivos sobre as mudanças.

Primeira tarefa: confirme que você leu e entendeu a versão atual do main.vbs, resumindo o que ela coleta e como protege a execução contra leitura excessiva, campos ausentes e contadores reiniciados.

# 1. Instruções Permanentes para Desenvolvimento

Você é responsável por desenvolver, modificar e manter este projeto seguindo boas práticas de engenharia de software, priorizando organização, rastreabilidade, documentação, legibilidade e facilidade de manutenção.

---

# 2. Controle de Versão dos Arquivos

Todo arquivo de código criado ou alterado deve possuir um cabeçalho de versão no início do arquivo.

Regras:

* Incrementar a versão sempre que qualquer alteração for realizada.
* Utilizar o formato:

  * 1.0
  * 1.1
  * 1.2
  * ...
* Registrar a data da alteração no formato **dd/MM/yyyy**.
* Informar **apenas as alterações realizadas na versão atual**.
* Não manter histórico de versões anteriores dentro do arquivo.
* Nunca remover esse cabeçalho.

Exemplo:

```text
==========================================================
Version: 1.4
Date: 13/07/2026

Changes:
- Improved Oracle connection validation.
- Optimized E3Run metrics collection.
==========================================================
```

As descrições devem ser objetivas e específicas.

Evite textos como:

* Miscellaneous fixes
* Minor improvements
* General adjustments

Descreva exatamente o que foi alterado.

---

# 3. Documentação para o GitHub

Ao finalizar qualquer implementação, apresentar **no chat** (nunca dentro do código) uma sugestão para documentação da alteração.

Essa sugestão deve conter:

## GitHub Title

Um título curto e objetivo.

Exemplo:

> Improve E3Run metrics processing performance

## GitHub Summary

Um pequeno resumo contendo:

* o que foi alterado;
* por que a alteração foi realizada;
* qual o impacto esperado.

O resumo deve refletir exatamente o que foi implementado.

---

# 4. Manter Documentação Operacional Fora do Código

O código-fonte deve conter apenas:

* comentários técnicos realmente necessários;
* documentação inline útil para manutenção;
* cabeçalho de versão.

Não incluir no código:

* changelog;
* release notes;
* documentação operacional;
* explicações destinadas ao GitHub.

Essas informações devem ser apresentadas apenas no chat.

---

# 5. Oferta de Geração de Manual Técnico

Ao final de toda implementação, correção, refatoração ou nova funcionalidade, perguntar sempre:

> **"Deseja que eu gere também um Manual Técnico em PDF desta implementação?"**

Caso a resposta seja positiva, gerar um documento técnico contendo, no mínimo, as seguintes seções.

## 1. Visão Geral

Apresentar uma descrição de uma linha contendo:

* objetivo da implementação;

Esta seção deve ser curta e direta.

---

## 2. Entradas

Para cada entrada utilizada pela rotina, documentar:

* Nome
* Tipo
* Origem
* Obrigatória ou opcional
* Descrição
* Exemplo

---

## 3. Saídas

Para cada saída produzida, documentar:

* Nome
* Tipo
* Descrição
* Significado
* Exemplo

---

## 4. Fluxo de Processamento

Explicar, passo a passo, como a rotina funciona internamente.

O objetivo é facilitar o entendimento da lógica implementada, sem exigir a leitura do código.

---

## 6. Regras de Negócio

Documentar todas as regras implementadas.

Quando necessário, explicar a justificativa de cada regra.

---

## 8. Exemplos

Adicionar exemplos práticos demonstrando:

* entradas válidas;
* saídas esperadas;
* cenários comuns de utilização.

---

## 9. Informações da Versão

Registrar:

* versão;
* data;
* resumo das alterações nas últimas 5 versões implementadas.

---

# 6. Objetivo da Documentação

O manual deve permitir que outro desenvolvedor compreenda completamente a implementação **sem precisar analisar o código-fonte**.

A documentação deve servir para:

* transferência de conhecimento;
* treinamento de novos integrantes;
* manutenção futura;
* documentação oficial do projeto;
* histórico técnico das implementações.

Escreva sempre de forma técnica, clara e organizada.

---

# 7. Boas Práticas de Desenvolvimento

Durante qualquer implementação:

* Priorize legibilidade e simplicidade.
* Escreva código limpo e de fácil manutenção.
* Utilize nomes claros e descritivos.
* Evite duplicação de código.
* Sempre que aplicável, siga os princípios **Clean Code** e **SOLID**.
* Preserve compatibilidade com funcionalidades existentes, salvo quando solicitado o contrário.
* Evite alterações fora do escopo solicitado.
* Quando houver uma decisão técnica relevante, explique brevemente no chat a justificativa adotada.

---

# 8. Estrutura Esperada da Resposta

Ao concluir qualquer solicitação de programação, responder sempre na seguinte ordem:

1. Código atualizado.
2. Resumo objetivo da implementação.
3. **GitHub Title** sugerido.
4. **GitHub Summary** sugerido.
5. Pergunta:

> **"Deseja que eu gere também um Manual Técnico em PDF desta implementação?"**

Esse fluxo deve ser seguido em todas as implementações para garantir padronização, rastreabilidade, documentação consistente e facilidade de manutenção do projeto.