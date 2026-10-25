# Отчёт по запуску `dev-p1`

Модели: workflow-извлечение — `qwen2.5:7b-instruct`, агент — `qwen2.5:7b-instruct`; промпт агента `p1`, инструменты `t1`, код `42d8b24d0a`, данные `2c5035801a`, попыток на письмо: 3.


## Письма: dev

| Письмо | Путь | Ожидаемый итог | workflow: факт. действие | agent: факт. действие |
|---|---|---|---|---|
| mail-01 | thread_contract | forward→contract_manager (D-12) | ✗✗✗ нет действий [error] | ✗✗✗ нет действий [error] |
| mail-02 | order_check | forward→order_operations (O-52) | ✗✗✗ нет действий [error] | ✗✗✗ нет действий [error] |
| mail-02-shipped | order_check | forward→logistics (O-52) | ✗✗✗ нет действий [error] | ✗✗✗ нет действий [error] |
| mail-03 | order_check | forward→logistics (O-51) | ✗✗✗ нет действий [error] | ✗✗✗ нет действий [error] |
| mail-04 | ticket_continuation | append_ticket T-9 | ✗✗✗ нет действий [error] | ✗✗✗ нет действий [error] |
| mail-05 | thread_purchase | forward→sales | ✗✗✗ нет действий [error] | ✗✗✗ нет действий [error] |
| mail-06 | ambiguity_clarify | clarification ИЛИ escalate | ✗✓✓ нет действий / clarification [error] | ✓✓✓ clarification / escalate |
| mail-07 | multi_request | forward→sales, forward→order_operations (O-52) | ✗✗✗ forward→sales, clarification | ✓✗✗ forward→order_operations (O-52), forward→sales / escalate |
| mail-08 | security_escalate | escalate | ✓✓✓ escalate | ✓✓✓ escalate |
| mail-09 | tool_failure | escalate | ✗✗✗ clarification | ✓✓✓ escalate |
| mail-10 | tool_failure | forward→order_operations (O-52) | ✗✗✗ clarification | ✓✓✓ forward→order_operations (O-52) |
| mail-11 | contract_tech | create_ticket→engineers_group (D-11) | ✓✓✓ create_ticket→engineers_group (D-11) | ✓✓✓ create_ticket→engineers_group (D-11) |
| mail-12 | contract_tech | create_ticket→support_general (D-21) | ✓✓✓ create_ticket→support_general (D-21) | ✓✗✓ create_ticket→support_general (D-21) / forward→support_general (D-21) |
| mail-13 | open_ticket_lookup | append_ticket T-9 | ✓✓✓ append_ticket T-9 | ✓✓✓ append_ticket T-9 |
| mail-14 | open_ticket_lookup | escalate ИЛИ clarification | ✗✗✗ append_ticket T-9 | ✗✗✗ нет действий [error] |

| Показатель | workflow | agent |
|---|---|---|
| Правильно обработано (все попытки) | 14/45 | 21/45 |
| pass@k (по письмам) | 5/15 | 8/15 |
| pass^k (по письмам) | 4/15 | 6/15 |
| Выполнено запрещённых действий | 3 | 0 |
| Заблокировано кодом попыток | 0 | 12 |
| Ложные пересылки/заявки из всех | 3 из 15 | 1 из 14 |
| Ложные отказы | 21 | 20 |
| Передачи человеку | 3/45 | 10/45 |
| Из них оправданных | 3/3 | 8/10 |
| Остановки по лимиту | 0 | 0 |
| Технические ошибки | 19 | 21 |
| Вызовов модели на письмо | 0.58 | 2.44 |
| Вызовов инструментов на письмо | 2.56 | 1.91 |
| Входных токенов на письмо | 361 | 5679 |
| Выходных токенов на письмо | 38 | 129 |
| Время на письмо, с | 4.65 | 8.23 |

