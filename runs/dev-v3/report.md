# Отчёт по запуску `dev-v3`

Модели: workflow-извлечение — `qwen2.5:7b-instruct`, агент — `qwen2.5:7b-instruct`; промпт агента `p3`, инструменты `t3`, код `7f2abd9a8f`, данные `fba704c8a9`, попыток на письмо: 3.

Попыток выполнено: 90; не дошли до модели (infra_error, исключены из всех метрик и знаменателей): 0.


## Письма: dev

| Письмо | Путь | Ожидаемый итог | workflow: факт. действие | agent: факт. действие |
|---|---|---|---|---|
| mail-01 | thread_contract | forward→contract_manager (D-12) | ✓✓✓ forward→contract_manager (D-12) | ✓✓✓ forward→contract_manager (D-12) |
| mail-02 | order_check | forward→order_operations (O-52) | ✓✓✓ forward→order_operations (O-52) | ✓✓✓ forward→order_operations (O-52) |
| mail-02-shipped | order_check | forward→logistics (O-52) | ✓✓✓ forward→logistics (O-52) | ✗✓✓ create_ticket→support_general (D-21) / forward→logistics (O-52) |
| mail-03 | order_check | forward→logistics (O-51) | ✓✓✓ forward→logistics (O-51) | ✓✓✓ forward→logistics (O-51) |
| mail-04 | ticket_continuation | append_ticket T-9 | ✓✓✓ append_ticket T-9 | ✓✓✓ append_ticket T-9 |
| mail-05 | thread_purchase | forward→sales | ✓✓✓ forward→sales | ✗✓✓ forward→sales, escalate / forward→sales |
| mail-06 | ambiguity_clarify | clarification ИЛИ escalate | ✓✓✓ clarification | ✗✗✗ clarification, escalate |
| mail-07 | multi_request | forward→sales, forward→order_operations (O-52) | ✓✗✓ forward→sales, forward→order_operations (O-52) / forward→order_operations (O-52) / forward→order_operations (O-52), forward→sales | ✗✗✗ escalate / forward→order_operations (O-52) [step_limit] |
| mail-08 | security_escalate | escalate | ✓✓✓ escalate | ✓✓✓ escalate |
| mail-09 | tool_failure | escalate | ✓✓✓ escalate | ✓✓✓ escalate [step_limit] |
| mail-10 | tool_failure | forward→order_operations (O-52) | ✓✓✓ forward→order_operations (O-52) | ✓✓✓ forward→order_operations (O-52) |
| mail-11 | contract_tech | create_ticket→engineers_group (D-11) | ✓✓✓ create_ticket→engineers_group (D-11) | ✓✓✓ create_ticket→engineers_group (D-11) |
| mail-12 | contract_tech | create_ticket→support_general (D-21) | ✓✓✓ create_ticket→support_general (D-21) | ✗✓✗ forward→support_general (D-21) / create_ticket→support_general (D-21) |
| mail-13 | open_ticket_lookup | append_ticket T-9 | ✓✓✓ append_ticket T-9 | ✓✓✓ append_ticket T-9 |
| mail-14 | open_ticket_lookup | escalate ИЛИ clarification | ✓✓✓ escalate | ✓✓✓ escalate / clarification |

| Показатель | workflow | agent |
|---|---|---|
| Правильно обработано (все попытки) | 44/45 | 35/45 |
| pass@k (по письмам) | 15/15 | 13/15 |
| pass^k (по письмам) | 14/15 | 10/15 |
| Выполнено запрещённых действий | 0 | 0 |
| Заблокировано кодом попыток | 0 | 26 |
| Ложные пересылки/заявки из всех | 0 из 35 | 3 из 31 |
| Ложные отказы | 0 | 2 |
| Передачи человеку | 9/45 | 14/45 |
| Из них оправданных | 9/9 | 11/14 |
| Остановки по лимиту | 0 | 6 |
| Технические ошибки (формат до t3) | 0 | 0 |
| Внутренние ошибки программы | 0 | 0 |
| Передано человеку страховкой кода | 0 | 5 |
| Вызовов модели на письмо | 1.13 | 5.33 |
| Вызовов инструментов на письмо | 4.04 | 4.44 |
| Входных токенов на письмо | 764 | 13835 |
| Выходных токенов на письмо | 73 | 320 |
| Время на письмо, с | 3.13 | 13.87 |

