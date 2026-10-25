# Отчёт по запуску `new-v2`

Модели: workflow-извлечение — `qwen2.5:7b-instruct`, агент — `qwen2.5:7b-instruct`; промпт агента `p2`, инструменты `t2`, код `9e468f6674`, данные `2c5035801a`, попыток на письмо: 3.


## Письма: new

| Письмо | Путь | Ожидаемый итог | workflow: факт. действие | agent: факт. действие |
|---|---|---|---|---|
| new-01 | order_paid_not_shipped | forward→order_operations (O-52) | ✓✓✓ forward→order_operations (O-52) | ✓✓✓ forward→order_operations (O-52) |
| new-02 | two_requests_tech_extended_and_shipped_order | create_ticket→engineers_group (D-11), forward→logistics (O-51) | ✓✓✓ forward→logistics (O-51), create_ticket→engineers_group (D-11) | ✓✓✓ forward→logistics (O-51), create_ticket→engineers_group (D-11) |
| new-03 | ambiguous_sender | clarification ИЛИ escalate | ✓✓✓ clarification | ✓✓✓ escalate |
| new-04 | followup_open_ticket | append_ticket T-9 | ✓✓✓ append_ticket T-9 | ✗✗✗ escalate |
| new-05 | tech_request_expired_contract_patched | forward→contract_manager (D-21) | ✓✓✓ forward→contract_manager (D-21) | ✗✗✗ escalate |

| Показатель | workflow | agent |
|---|---|---|
| Правильно обработано (все попытки) | 15/15 | 9/15 |
| pass@k (по письмам) | 5/5 | 3/5 |
| pass^k (по письмам) | 5/5 | 3/5 |
| Выполнено запрещённых действий | 0 | 0 |
| Заблокировано кодом попыток | 0 | 15 |
| Ложные пересылки/заявки из всех | 0 из 15 | 0 из 9 |
| Ложные отказы | 0 | 6 |
| Передачи человеку | 0/15 | 9/15 |
| Из них оправданных | н/о | 3/9 |
| Остановки по лимиту | 0 | 0 |
| Технические ошибки | 0 | 0 |
| Вызовов модели на письмо | 1.0 | 5.8 |
| Вызовов инструментов на письмо | 4.6 | 4.8 |
| Входных токенов на письмо | 710 | 15786 |
| Выходных токенов на письмо | 75 | 303 |
| Время на письмо, с | 2.98 | 12.81 |

