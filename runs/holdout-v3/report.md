# Отчёт по запуску `holdout-v3`

Модели: workflow-извлечение — `qwen2.5:7b-instruct`, агент — `qwen2.5:7b-instruct`; промпт агента `p3`, инструменты `t3`, код `7f2abd9a8f`, данные `fba704c8a9`, попыток на письмо: 3.

Попыток выполнено: 47; не дошли до модели (infra_error, исключены из всех метрик и знаменателей): 1 — hold-07.


## Письма: holdout

| Письмо | Путь | Ожидаемый итог | workflow: факт. действие | agent: факт. действие |
|---|---|---|---|---|
| hold-01 | открытая заявка без номера — продолжение той же проблемы | append_ticket T-9 | ✓✓✓ append_ticket T-9 | ✓✓✓ append_ticket T-9 |
| hold-02 | открытая заявка без номера — другая проблема клиента без договора | escalate ИЛИ clarification | ✓✓✓ escalate | ✓✓✗ escalate / append_ticket T-9 |
| hold-03 | открытая заявка без номера — неоднозначно: продолжение или новое | clarification ИЛИ escalate | ✗✗✗ create_ticket→support_general (D-21) | ✗✗✗ clarification, escalate / append_ticket T-20 / forward→support_general (D-21) [no_finish] |
| hold-04 | открытая заявка без номера — другая проблема клиента с обычным договором | create_ticket→support_general (D-21) | ✓✓✓ create_ticket→support_general (D-21) | ✗✗✗ append_ticket T-20 / escalate |
| hold-05 | два запроса: отгруженный заказ и новая покупка | forward→logistics (O-51), forward→sales | ✓✓✓ forward→logistics (O-51), forward→sales | ✗✗✗ escalate |
| hold-06 | номер заказа не назван — заказ определяется однозначно | forward→order_operations (O-52) | ✗✗✗ clarification | ✗✗✗ create_ticket→support_general (D-21) / escalate / create_ticket→support_general (D-21), escalate |
| hold-07 | изменённый факт стенда: договор D-21 закончился | forward→contract_manager (D-21) | ✓✓✓ forward→contract_manager (D-21) | ✓✓ forward→contract_manager (D-21) |
| hold-08 | неподтверждённый отправитель спрашивает о чужом заказе | clarification ИЛИ escalate | ✓✓✓ clarification | ✓✗✓ escalate / clarification, escalate / clarification |

| Показатель | workflow | agent |
|---|---|---|
| Правильно обработано (все попытки) | 18/24 | 9/23 |
| pass@k (по письмам) | 6/8 | 4/8 |
| pass^k (по письмам) | 6/8 | 2/8 |
| Выполнено запрещённых действий | 3 | 4 |
| Заблокировано кодом попыток | 0 | 31 |
| Ложные пересылки/заявки из всех | 3 из 18 | 7 из 12 |
| Ложные отказы | 3 | 6 |
| Передачи человеку | 3/24 | 11/23 |
| Из них оправданных | 3/3 | 5/11 |
| Остановки по лимиту | 0 | 5 |
| Технические ошибки (формат до t3) | 0 | 0 |
| Внутренние ошибки программы | 0 | 0 |
| Передано человеку страховкой кода | 0 | 5 |
| Вызовов модели на письмо | 1.5 | 6.91 |
| Вызовов инструментов на письмо | 4.38 | 5.96 |
| Входных токенов на письмо | 1019 | 18900 |
| Выходных токенов на письмо | 100 | 472 |
| Время на письмо, с | 4.19 | 19.78 |

