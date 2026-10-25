# Отчёт по запуску `new-final`

Модели: workflow-извлечение — `qwen2.5:7b-instruct`, агент — `qwen2.5:7b-instruct`; промпт агента `p2`, инструменты `t1`, код `42d8b24d0a`, данные `2c5035801a`, попыток на письмо: 3.


## Письма: new

| Письмо | Путь | Ожидаемый итог | workflow: факт. действие | agent: факт. действие |
|---|---|---|---|---|
| new-01 | order_paid_not_shipped | forward→order_operations (O-52) | ✗✗✗ clarification | ✓✓✓ forward→order_operations (O-52) |
| new-02 | two_requests_tech_extended_and_shipped_order | create_ticket→engineers_group (D-11), forward→logistics (O-51) | ✗✗✗ clarification, create_ticket→engineers_group (D-11) | ✗✓✓ clarification, create_ticket→engineers_group (D-11) / forward→logistics (O-51), create_ticket→engineers_group (D-11) |
| new-03 | ambiguous_sender | clarification ИЛИ escalate | ✓✓✓ clarification | ✓✓✓ clarification / escalate [step_limit] |
| new-04 | followup_open_ticket | append_ticket T-9 | ✓✓✓ append_ticket T-9 | ✗✗✗ escalate |
| new-05 | tech_request_expired_contract_patched | forward→contract_manager (D-21) | ✓✓✓ forward→contract_manager (D-21) | ✗✗✗ escalate |

| Показатель | workflow | agent |
|---|---|---|
| Правильно обработано (все попытки) | 9/15 | 8/15 |
| pass@k (по письмам) | 3/5 | 3/5 |
| pass^k (по письмам) | 3/5 | 2/5 |
| Выполнено запрещённых действий | 0 | 0 |
| Заблокировано кодом попыток | 0 | 25 |
| Ложные пересылки/заявки из всех | 0 из 9 | 0 из 8 |
| Ложные отказы | 3 | 6 |
| Передачи человеку | 0/15 | 8/15 |
| Из них оправданных | н/о | 2/8 |
| Остановки по лимиту | 0 | 1 |
| Технические ошибки | 0 | 0 |
| Вызовов модели на письмо | 1.0 | 6.33 |
| Вызовов инструментов на письмо | 4.2 | 5.47 |
| Входных токенов на письмо | 710 | 17401 |
| Выходных токенов на письмо | 75 | 361 |
| Время на письмо, с | 2.98 | 15.1 |

