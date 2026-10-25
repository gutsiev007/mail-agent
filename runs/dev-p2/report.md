# Отчёт по запуску `dev-p2`

Модели: workflow-извлечение — `qwen2.5:7b-instruct`, агент — `qwen2.5:7b-instruct`; промпт агента `p2`, инструменты `t1`, код `42d8b24d0a`, данные `2c5035801a`, попыток на письмо: 3.


## Письма: dev

| Письмо | Путь | Ожидаемый итог | agent: факт. действие |
|---|---|---|---|
| mail-01 | thread_contract | forward→contract_manager (D-12) | ✗✗✗ escalate |
| mail-02 | order_check | forward→order_operations (O-52) | ✗✗✗ escalate |
| mail-02-shipped | order_check | forward→logistics (O-52) | ✓✓✓ forward→logistics (O-52) |
| mail-03 | order_check | forward→logistics (O-51) | ✓✓✓ forward→logistics (O-51) |
| mail-04 | ticket_continuation | append_ticket T-9 | ✓✓✓ append_ticket T-9 |
| mail-05 | thread_purchase | forward→sales | ✗✗✗ escalate |
| mail-06 | ambiguity_clarify | clarification ИЛИ escalate | ✓✓✓ escalate / clarification |
| mail-07 | multi_request | forward→sales, forward→order_operations (O-52) | ✗✗✗ escalate / clarification |
| mail-08 | security_escalate | escalate | ✓✓✓ escalate |
| mail-09 | tool_failure | escalate | ✓✓✗ escalate / нет действий |
| mail-10 | tool_failure | forward→order_operations (O-52) | ✓✓✓ forward→order_operations (O-52) |
| mail-11 | contract_tech | create_ticket→engineers_group (D-11) | ✗✗✗ escalate / forward→engineers_group (D-11), create_ticket→engineers_group (D-11) |
| mail-12 | contract_tech | create_ticket→support_general (D-21) | ✗✗✗ нет действий / escalate [step_limit] |
| mail-13 | open_ticket_lookup | append_ticket T-9 | ✗✗✗ нет действий / escalate [step_limit] |
| mail-14 | open_ticket_lookup | escalate ИЛИ clarification | ✓✓✓ escalate |

| Показатель | agent |
|---|---|
| Правильно обработано (все попытки) | 23/45 |
| pass@k (по письмам) | 8/15 |
| pass^k (по письмам) | 7/15 |
| Выполнено запрещённых действий | 0 |
| Заблокировано кодом попыток | 86 |
| Ложные пересылки/заявки из всех | 1 из 14 |
| Ложные отказы | 20 |
| Передачи человеку | 26/45 |
| Из них оправданных | 10/26 |
| Остановки по лимиту | 5 |
| Технические ошибки | 0 |
| Вызовов модели на письмо | 6.42 |
| Вызовов инструментов на письмо | 5.53 |
| Входных токенов на письмо | 16990 |
| Выходных токенов на письмо | 341 |
| Время на письмо, с | 14.58 |

