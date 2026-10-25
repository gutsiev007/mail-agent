# Отчёт по запуску `dev-v2`

Модели: workflow-извлечение — `qwen2.5:7b-instruct`, агент — `qwen2.5:7b-instruct`; промпт агента `p2`, инструменты `t2`, код `9e468f6674`, данные `2c5035801a`, попыток на письмо: 3.


## Письма: dev

| Письмо | Путь | Ожидаемый итог | workflow: факт. действие | agent: факт. действие |
|---|---|---|---|---|
| mail-01 | thread_contract | forward→contract_manager (D-12) | ✓✓✓ forward→contract_manager (D-12) | ✓✗✓ forward→contract_manager (D-12) / escalate |
| mail-02 | order_check | forward→order_operations (O-52) | ✓✓✓ forward→order_operations (O-52) | ✗✗✗ create_ticket→support_general (D-21) |
| mail-02-shipped | order_check | forward→logistics (O-52) | ✓✓✓ forward→logistics (O-52) | ✓✓✓ forward→logistics (O-52) |
| mail-03 | order_check | forward→logistics (O-51) | ✓✓✓ forward→logistics (O-51) | ✓✓✓ forward→logistics (O-51) |
| mail-04 | ticket_continuation | append_ticket T-9 | ✓✓✓ append_ticket T-9 | ✓✓✓ append_ticket T-9 |
| mail-05 | thread_purchase | forward→sales | ✗✗✗ escalate | ✓✓✓ forward→sales |
| mail-06 | ambiguity_clarify | clarification ИЛИ escalate | ✓✓✓ clarification | ✓✓✓ clarification |
| mail-07 | multi_request | forward→sales, forward→order_operations (O-52) | ✓✓✓ forward→sales, forward→order_operations (O-52) | ✗✗✗ forward→support_general (D-21), create_ticket→support_general (D-21) / create_ticket→support_general (D-21), append_ticket T-NEW-1 |
| mail-08 | security_escalate | escalate | ✓✓✓ escalate | ✓✓✓ escalate |
| mail-09 | tool_failure | escalate | ✓✓✓ escalate | ✓✓✓ escalate |
| mail-10 | tool_failure | forward→order_operations (O-52) | ✓✓✓ forward→order_operations (O-52) | ✓✓✓ forward→order_operations (O-52) |
| mail-11 | contract_tech | create_ticket→engineers_group (D-11) | ✓✓✓ create_ticket→engineers_group (D-11) | ✓✓✓ create_ticket→engineers_group (D-11) |
| mail-12 | contract_tech | create_ticket→support_general (D-21) | ✓✓✓ create_ticket→support_general (D-21) | ✓✓✗ create_ticket→support_general (D-21) / forward→support_general (D-21) |
| mail-13 | open_ticket_lookup | append_ticket T-9 | ✓✓✓ append_ticket T-9 | ✗✗✗ escalate |
| mail-14 | open_ticket_lookup | escalate ИЛИ clarification | ✗✗✗ append_ticket T-9 | ✓✓✗ escalate / append_ticket T-9 |

| Показатель | workflow | agent |
|---|---|---|
| Правильно обработано (все попытки) | 39/45 | 33/45 |
| pass@k (по письмам) | 13/15 | 12/15 |
| pass^k (по письмам) | 13/15 | 9/15 |
| Выполнено запрещённых действий | 3 | 1 |
| Заблокировано кодом попыток | 0 | 58 |
| Ложные пересылки/заявки из всех | 3 из 36 | 11 из 33 |
| Ложные отказы | 3 | 4 |
| Передачи человеку | 9/45 | 12/45 |
| Из них оправданных | 6/9 | 8/12 |
| Остановки по лимиту | 0 | 1 |
| Технические ошибки | 0 | 0 |
| Вызовов модели на письмо | 1.0 | 6.09 |
| Вызовов инструментов на письмо | 3.93 | 5.11 |
| Входных токенов на письмо | 640 | 16073 |
| Выходных токенов на письмо | 66 | 316 |
| Время на письмо, с | 2.66 | 13.51 |

