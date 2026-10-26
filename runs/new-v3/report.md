# Отчёт по запуску `new-v3`

Модели: workflow-извлечение — `qwen2.5:7b-instruct`, агент — `qwen2.5:7b-instruct`; промпт агента `p3`, инструменты `t3`, код `7f2abd9a8f`, данные `fba704c8a9`, попыток на письмо: 3.

Попыток выполнено: 30; не дошли до модели (infra_error, исключены из всех метрик и знаменателей): 0.


## Письма: new

| Письмо | Путь | Ожидаемый итог | workflow: факт. действие | agent: факт. действие |
|---|---|---|---|---|
| new-01 | order_paid_not_shipped | forward→order_operations (O-52) | ✓✓✓ forward→order_operations (O-52) | ✓✓✓ forward→order_operations (O-52) |
| new-02 | two_requests_tech_extended_and_shipped_order | create_ticket→engineers_group (D-11), forward→logistics (O-51) | ✓✓✓ forward→logistics (O-51), create_ticket→engineers_group (D-11) | ✗✗✓ create_ticket→engineers_group (D-11), append_ticket T-NEW-1 / forward→logistics (O-51), create_ticket→engineers_group (D-11) |
| new-03 | ambiguous_sender | clarification ИЛИ escalate | ✓✓✓ clarification | ✓✗✗ escalate / clarification, clarification, escalate / clarification, escalate [step_limit] |
| new-04 | followup_open_ticket | append_ticket T-9 | ✓✓✓ append_ticket T-9 | ✓✓✓ append_ticket T-9 |
| new-05 | tech_request_expired_contract_patched | forward→contract_manager (D-21) | ✓✓✓ forward→contract_manager (D-21) | ✓✓✓ forward→contract_manager (D-21) |

| Показатель | workflow | agent |
|---|---|---|
| Правильно обработано (все попытки) | 15/15 | 11/15 |
| pass@k (по письмам) | 5/5 | 5/5 |
| pass^k (по письмам) | 5/5 | 3/5 |
| Выполнено запрещённых действий | 0 | 0 |
| Заблокировано кодом попыток | 0 | 7 |
| Ложные пересылки/заявки из всех | 0 из 15 | 2 из 15 |
| Ложные отказы | 0 | 0 |
| Передачи человеку | 0/15 | 3/15 |
| Из них оправданных | н/о | 3/3 |
| Остановки по лимиту | 0 | 1 |
| Технические ошибки (формат до t3) | 0 | 0 |
| Внутренние ошибки программы | 0 | 0 |
| Передано человеку страховкой кода | 0 | 1 |
| Вызовов модели на письмо | 1.2 | 6.2 |
| Вызовов инструментов на письмо | 4.6 | 5.2 |
| Входных токенов на письмо | 885 | 16992 |
| Выходных токенов на письмо | 92 | 393 |
| Время на письмо, с | 3.86 | 16.46 |

