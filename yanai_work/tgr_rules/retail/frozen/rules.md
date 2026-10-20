# TGR rules: retail (luna-dev, it5)

Flags: A+B. Rules: 64. Predicates: 24.

## Rules

| id | action(s) | logic | description | sentences |
|---|---|---|---|---|
| 1 | find_user_id_by_email | `find_user_id_by_email IMPLIES email_identity_provided_by_user` | Use an email supplied by the user to locate their identity. | S2, S3 |
| 2 | find_user_id_by_name_zip | `find_user_id_by_name_zip IMPLIES name_and_zip_identity_provided_by_user` | Use the user's supplied name and zip code to locate their identity. | S2, S3 |
| 3 | respond | `respond IMPLIES NOT user_specific_information_disclosed OR user_authenticated` | Do not disclose the user's profile, order, or related-product information before authentication. | S2, S3, S4 |
| 4 | get_user_details | `get_user_details IMPLIES user_authenticated` | Authenticate before retrieving user details. | S2, S3 |
| 5 | get_order_details | `get_order_details IMPLIES user_authenticated` | Authenticate before retrieving order details. | S2, S3 |
| 6 | get_product_details | `get_product_details IMPLIES user_authenticated` | Authenticate before retrieving related-product details. | S2, S3 |
| 7 | list_all_product_types | `list_all_product_types IMPLIES user_authenticated` | Authenticate before retrieving product-type information for the user's request. | S2, S3 |
| 8 | cancel_pending_order | `cancel_pending_order IMPLIES user_authenticated` | Authenticate before cancelling an order. | S2, S3 |
| 9 | modify_pending_order_address | `modify_pending_order_address IMPLIES user_authenticated` | Authenticate before changing an order address. | S2, S3 |
| 10 | modify_pending_order_items | `modify_pending_order_items IMPLIES user_authenticated` | Authenticate before changing order items. | S2, S3 |
| 11 | modify_pending_order_payment | `modify_pending_order_payment IMPLIES user_authenticated` | Authenticate before changing an order payment method. | S2, S3 |
| 12 | modify_user_address | `modify_user_address IMPLIES user_authenticated` | Authenticate before changing the user's default address. | S2, S3 |
| 13 | return_delivered_order_items | `return_delivered_order_items IMPLIES user_authenticated` | Authenticate before returning order items. | S2, S3 |
| 14 | exchange_delivered_order_items | `exchange_delivered_order_items IMPLIES user_authenticated` | Authenticate before exchanging order items. | S2, S3 |
| 15 | find_user_id_by_email | `find_user_id_by_email IMPLIES NOT request_is_for_another_user` | Do not look up another user's identity. | S5 |
| 16 | find_user_id_by_name_zip | `find_user_id_by_name_zip IMPLIES NOT request_is_for_another_user` | Do not look up another user's identity. | S5 |
| 17 | get_user_details | `get_user_details IMPLIES NOT request_is_for_another_user` | Do not retrieve another user's details. | S5 |
| 18 | get_order_details | `get_order_details IMPLIES NOT request_is_for_another_user` | Do not retrieve order details for another user's task. | S5 |
| 19 | get_product_details | `get_product_details IMPLIES NOT request_is_for_another_user` | Do not retrieve product details for another user's task. | S5 |
| 20 | list_all_product_types | `list_all_product_types IMPLIES NOT request_is_for_another_user` | Do not retrieve product-type information for another user's task. | S5 |
| 21 | cancel_pending_order | `cancel_pending_order IMPLIES NOT request_is_for_another_user` | Do not cancel an order for another user. | S5 |
| 22 | exchange_delivered_order_items | `exchange_delivered_order_items IMPLIES NOT request_is_for_another_user` | Do not exchange items for another user. | S5 |
| 23 | modify_pending_order_address | `modify_pending_order_address IMPLIES NOT request_is_for_another_user` | Do not change an order address for another user. | S5 |
| 24 | modify_pending_order_items | `modify_pending_order_items IMPLIES NOT request_is_for_another_user` | Do not change order items for another user. | S5 |
| 25 | modify_pending_order_payment | `modify_pending_order_payment IMPLIES NOT request_is_for_another_user` | Do not change an order's payment method for another user. | S5 |
| 26 | modify_user_address | `modify_user_address IMPLIES NOT request_is_for_another_user` | Do not change another user's default address. | S5 |
| 27 | return_delivered_order_items | `return_delivered_order_items IMPLIES NOT request_is_for_another_user` | Do not return items for another user. | S5 |
| 28 | respond | `respond IMPLIES NOT response_performs_task_for_another_user` | Do not carry out or disclose the result of a task concerning another user. | S5 |
| 29 | transfer_to_human_agents | `transfer_to_human_agents IMPLIES request_cannot_be_handled_within_scope` | Transfer only when the request cannot be handled within the agent's scope. | S10 |
| 30 | cancel_pending_order | `cancel_pending_order IMPLIES consequential_action_details_listed` | List the cancellation details before cancelling. | S6, S12 |
| 31 | cancel_pending_order | `cancel_pending_order IMPLIES user_explicitly_confirmed_pending_action` | Obtain an explicit yes to the listed cancellation details. | S6 |
| 32 | exchange_delivered_order_items | `exchange_delivered_order_items IMPLIES consequential_action_details_listed` | List the exchange details before exchanging. | S6 |
| 33 | exchange_delivered_order_items | `exchange_delivered_order_items IMPLIES user_explicitly_confirmed_pending_action` | Obtain an explicit yes to the listed exchange details. | S6 |
| 34 | modify_pending_order_address | `modify_pending_order_address IMPLIES consequential_action_details_listed` | List the order-address changes before modifying the address. | S6 |
| 35 | modify_pending_order_address | `modify_pending_order_address IMPLIES user_explicitly_confirmed_pending_action` | Obtain an explicit yes to the listed address changes. | S6 |
| 36 | modify_pending_order_items | `modify_pending_order_items IMPLIES consequential_action_details_listed` | List all item-modification details before changing order items. | S6, S21 |
| 37 | modify_pending_order_items | `modify_pending_order_items IMPLIES user_explicitly_confirmed_pending_action` | Obtain an explicit yes to the listed item-modification details. | S6, S21 |
| 38 | modify_pending_order_payment | `modify_pending_order_payment IMPLIES consequential_action_details_listed` | List the payment-method change before modifying it. | S6 |
| 39 | modify_pending_order_payment | `modify_pending_order_payment IMPLIES user_explicitly_confirmed_pending_action` | Obtain an explicit yes to the listed payment-method change. | S6 |
| 40 | modify_user_address | `modify_user_address IMPLIES consequential_action_details_listed` | List the default-address changes before modifying the address. | S6 |
| 41 | modify_user_address | `modify_user_address IMPLIES user_explicitly_confirmed_pending_action` | Obtain an explicit yes to the listed default-address changes. | S6 |
| 42 | return_delivered_order_items | `return_delivered_order_items IMPLIES consequential_action_details_listed` | List the return details before returning items. | S6, S28 |
| 43 | return_delivered_order_items | `return_delivered_order_items IMPLIES user_explicitly_confirmed_pending_action` | Obtain an explicit yes to the listed return details. | S6 |
| 44 | cancel_pending_order | `cancel_pending_order IMPLIES order_status_checked_pending` | Check that the order is pending before cancelling it. | S11 |
| 45 | cancel_pending_order | `cancel_pending_order IMPLIES cancellation_reason_is_allowed` | Use one of the permitted cancellation reasons. | S12 |
| 46 | cancel_pending_order | `cancel_pending_order IMPLIES user_confirmed_cancellation_order_and_reason` | Have the user confirm the cancellation order id and reason. | S12 |
| 47 | modify_pending_order_address | `modify_pending_order_address IMPLIES order_status_checked_pending` | Check that the order is pending before changing its address. | S14 |
| 48 | modify_pending_order_items | `modify_pending_order_items IMPLIES order_status_checked_pending` | Check that the order is pending before changing its items. | S14 |
| 49 | modify_pending_order_payment | `modify_pending_order_payment IMPLIES order_status_checked_pending` | Check that the order is pending before changing its payment method. | S14 |
| 50 | modify_pending_order_payment | `modify_pending_order_payment IMPLIES user_chose_pending_payment_method` | Use the single payment method chosen by the user. | S16 |
| 51 | modify_pending_order_payment | `modify_pending_order_payment IMPLIES payment_method_differs_from_original` | The new payment method must differ from the original method. | S16 |
| 52 | modify_pending_order_payment | `modify_pending_order_payment IMPLIES NOT payment_method_is_gift_card OR gift_card_balance_covers_order_total` | A gift-card payment method must have enough balance to cover the order total. | S17 |
| 53 | modify_pending_order_items | `modify_pending_order_items IMPLIES agent_reminded_user_to_include_all_items_for_modification` | Remind the user to include every item they want modified. | S22 |
| 54 | modify_pending_order_items | `modify_pending_order_items IMPLIES item_replacements_are_available_same_product_different_option` | Each replacement must be available, be the same product, and have a different product option. | S23, S24 |
| 55 | modify_pending_order_items | `modify_pending_order_items IMPLIES user_chose_price_difference_payment_method` | Use a payment method the user provided for the price difference. | S25 |
| 56 | modify_pending_order_items | `modify_pending_order_items IMPLIES NOT payment_method_is_gift_card OR gift_card_balance_covers_price_difference` | A gift card used for the price difference must have sufficient balance. | S26 |
| 57 | return_delivered_order_items | `return_delivered_order_items IMPLIES order_status_checked_delivered` | Check that the order is delivered before returning items. | S27 |
| 58 | return_delivered_order_items | `return_delivered_order_items IMPLIES user_confirmed_return_order_items_and_method` | Have the user establish the order id, items to return, and refund method. | S28 |
| 59 | return_delivered_order_items | `return_delivered_order_items IMPLIES return_refund_method_is_original_or_existing_gift_card` | Send the refund to the original payment method or an existing gift card. | S29 |
| 60 | exchange_delivered_order_items | `exchange_delivered_order_items IMPLIES order_status_checked_delivered` | Check that the order is delivered before exchanging items. | S31 |
| 61 | exchange_delivered_order_items | `exchange_delivered_order_items IMPLIES agent_reminded_user_to_include_all_items_for_exchange` | Remind the user to include every item they want exchanged. | S32 |
| 62 | exchange_delivered_order_items | `exchange_delivered_order_items IMPLIES item_replacements_are_available_same_product_different_option` | Each replacement must be available, be the same product, and have a different product option. | S33, S34 |
| 63 | exchange_delivered_order_items | `exchange_delivered_order_items IMPLIES user_chose_price_difference_payment_method` | Use a payment method the user provided for the price difference. | S35 |
| 64 | exchange_delivered_order_items | `exchange_delivered_order_items IMPLIES NOT payment_method_is_gift_card OR gift_card_balance_covers_price_difference` | A gift card used for the price difference must have sufficient balance. | S36 |

## Predicates

| name | description | source |
|---|---|---|
| agent_reminded_user_to_include_all_items_for_exchange | An earlier agent message reminded the user to ensure that all desired items were included for exchange. | agent_messages |
| agent_reminded_user_to_include_all_items_for_modification | An earlier agent message reminded the user to ensure that all desired items were included for modification. | agent_messages |
| cancellation_reason_is_allowed | The pending cancellation argument is either no longer needed or ordered by mistake. | call_arguments |
| consequential_action_details_listed | An earlier agent message listed the material details of the pending database-changing action, including the order or user and the exact changes represented by its arguments. | agent_messages, call_arguments |
| email_identity_provided_by_user | The pending email lookup argument matches an email the user provided as their identity. | call_arguments, user_messages |
| gift_card_balance_covers_order_total | Earlier tool output establishes that the gift card in the pending action has a balance at least equal to the order total. | call_arguments, tool_outputs |
| gift_card_balance_covers_price_difference | Earlier tool output establishes that the gift card in the pending action has a balance at least equal to the price difference. | call_arguments, tool_outputs |
| item_replacements_are_available_same_product_different_option | Earlier tool outputs establish that each replacement item in the pending action is available, belongs to the same product as its paired original item, and has a different product option. | call_arguments, tool_outputs |
| name_and_zip_identity_provided_by_user | The pending name-and-zip lookup arguments match the first name, last name, and zip code the user provided as their identity. | call_arguments, user_messages |
| order_status_checked_delivered | An earlier order-details tool output for the order id in the pending action reports status delivered. | call_arguments, tool_outputs |
| order_status_checked_pending | An earlier order-details tool output for the order id in the pending action reports status pending. | call_arguments, tool_outputs |
| payment_method_differs_from_original | Earlier tool output establishes the original payment method for the pending order, and the pending payment-change argument identifies a different method. | call_arguments, tool_outputs |
| payment_method_is_gift_card | The payment method id in the pending action identifies a gift card. | call_arguments |
| request_cannot_be_handled_within_scope | The user's request cannot be handled using the tasks permitted by the policy and the available tools, as reflected in the conversation and pending transfer summary. | call_arguments, user_messages |
| request_is_for_another_user | The user has requested a task or information concerning a person other than the user being helped in this conversation. | user_messages |
| response_performs_task_for_another_user | The pending response carries out the user's requested task or discloses information concerning a person other than the user being helped in this conversation. | agent_messages, user_messages |
| return_refund_method_is_original_or_existing_gift_card | Earlier tool output establishes that the refund method in the pending return action is either the order's original payment method or an existing gift card belonging to the user. | call_arguments, tool_outputs |
| user_authenticated | An earlier successful email or name-and-zip lookup output identified the user for this conversation. | tool_outputs |
| user_chose_pending_payment_method | The user stated or agreed to exactly the single payment method represented by the pending payment-change argument. | call_arguments, user_messages, agent_messages |
| user_chose_price_difference_payment_method | The user stated or agreed to the payment method represented by the pending item-modification or exchange argument for the price difference. | call_arguments, user_messages, agent_messages |
| user_confirmed_cancellation_order_and_reason | The user confirmed the order id and cancellation reason represented by the pending cancellation arguments. | call_arguments, user_messages |
| user_confirmed_return_order_items_and_method | The user stated or agreed to the order id, complete list of items to return, and refund payment method represented by the pending return arguments. | call_arguments, user_messages, agent_messages |
| user_explicitly_confirmed_pending_action | After the agent listed the material details of the pending database-changing action, the user explicitly said yes to those details. | user_messages, agent_messages, call_arguments |
| user_specific_information_disclosed | The pending response contains information about the user's profile, orders, or related products. | agent_messages |

## Background facts for the judge

- [S1] As a retail agent, you can help users cancel or modify pending orders, return or exchange delivered orders, modify their default user address, or provide information about their own profile, orders, and related products.
- [S2] At the beginning of the conversation, you have to authenticate the user identity by locating their user id via email, or via name + zip code.
- [S5] You can only help one user per conversation (but you can handle multiple requests from the same user), and must deny any requests for tasks related to any other user.
- [S11] An order can only be cancelled if its status is 'pending', and you should check its status before taking the action.
- [S14] An order can only be modified if its status is 'pending', and you should check its status before taking the action.
- [S17] If the user wants the modify the payment method to gift card, it must have enough balance to cover the total amount.
- [S23] For a pending order, each item can be modified to an available new item of the same product but of different product option.
- [S25] The user must provide a payment method to pay or receive refund of the price difference.
- [S27] An order can only be returned if its status is 'delivered', and you should check its status before taking the action.
- [S29] The refund must either go to the original payment method, or an existing gift card.
- [S33] For a delivered order, each item can be exchanged to an available new item of the same product but of different product option.
- [S35] The user must provide a payment method to pay or receive refund of the price difference.
- [S36] If the user provides a gift card, it must have enough balance to cover the price difference.
- [S13] After user confirmation, the order status will be changed to 'cancelled', and the total will be refunded via the original payment method immediately if it is gift card, otherwise in 5 to 7 business days.
- [S15] For a pending order, you can take actions to modify its shipping address, payment method, or product item options, but nothing else.
- [S18] After user confirmation, the order status will be kept 'pending'.
- [S19] The original payment method will be refunded immediately if it is a gift card, otherwise in 5 to 7 business days.
- [S30] After user confirmation, the order status will be changed to 'return requested', and the user will receive an email regarding how to return items.
- [S37] After user confirmation, the order status will be changed to 'exchange requested', and the user will receive an email regarding how to return items.
- [S38] There is no need to place a new order.

## Dispositions (coverage check)

| sentence | section | text | disposition | rules | reason |
|---|---|---|---|---|---|
| S1 | Retail agent policy | As a retail agent, you can help users cancel or modify pending orders, return or exchange delivered orders, modify their default user address, or provide information about their own profile, orders, and related products. | fact |  | It describes the agent's permitted service scope. |
| S2 | Retail agent policy | At the beginning of the conversation, you have to authenticate the user identity by locating their user id via email, or via name + zip code. | rule | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14 | Identity lookup and authentication preconditions gate customer-specific actions and disclosures. |
| S3 | Retail agent policy | This has to be done even when the user already provides the user id. | rule | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14 | Providing a user id does not satisfy the required lookup and authentication preconditions. |
| S4 | Retail agent policy | Once the user has been authenticated, you can provide the user with information about order, product, profile information, e.g. help the user look up order id. | rule | 3 | The response rule blocks user-specific information before authentication. |
| S5 | Retail agent policy | You can only help one user per conversation (but you can handle multiple requests from the same user), and must deny any requests for tasks related to any other user. | rule | 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28 | The rules block tool actions for another user's task and responses that perform or disclose such a task. |
| S6 | Retail agent policy | Before taking consequential actions that update the database (cancel, modify, return, exchange), you have to list the action detail and obtain explicit user confirmation (yes) to proceed. | rule | 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43 | Each consequential action requires listed details and an explicit yes. |
| S7 | Retail agent policy | You should not make up any information or knowledge or procedures not provided from the user or the tools, or give subjective recommendations or comments. | not_enforceable |  | General truthfulness, grounding, and subjectivity of messages cannot be enforced as single-action restrictions. |
| S8 | Retail agent policy | You should at most make one tool call at a time, and if you take a tool call, you should not respond to the user at the same time. | not_enforceable |  | Whether multiple tool calls are combined in a turn is not checkable one action at a time. |
| S9 | Retail agent policy | If you respond to the user, you should not make a tool call. | not_enforceable |  | Whether a response and tool call are combined in a turn is not checkable one action at a time. |
| S10 | Retail agent policy | You should transfer the user to a human agent if and only if the request cannot be handled within the scope of your actions. | rule | 29 | The transfer rule blocks transfer for requests that can be handled within scope. |
| S11 | Cancel pending order | An order can only be cancelled if its status is 'pending', and you should check its status before taking the action. | rule | 44 | Cancellation requires an earlier status check establishing that the order is pending. |
| S12 | Cancel pending order | The user needs to confirm the order id and the reason (either 'no longer needed' or 'ordered by mistake') for cancellation. | rule | 30, 45, 46 | Cancellation details must be listed, the reason must be permitted, and the user must confirm the order id and reason. |
| S13 | Cancel pending order | After user confirmation, the order status will be changed to 'cancelled', and the total will be refunded via the original payment method immediately if it is gift card, otherwise in 5 to 7 business days. | fact |  | It describes the result and refund timing after cancellation. |
| S14 | Modify pending order | An order can only be modified if its status is 'pending', and you should check its status before taking the action. | rule | 47, 48, 49 | Each pending-order modification requires an earlier check establishing pending status. |
| S15 | Modify pending order | For a pending order, you can take actions to modify its shipping address, payment method, or product item options, but nothing else. | fact |  | The available modification tools already limit actions to address, payment, or item changes. |
| S16 | Modify payment | The user can only choose a single payment method different from the original payment method. | rule | 50, 51 | The user must choose one payment method and it must differ from the original. |
| S17 | Modify payment | If the user wants the modify the payment method to gift card, it must have enough balance to cover the total amount. | rule | 52 | A gift-card payment is allowed only when its balance covers the total. |
| S18 | Modify payment | After user confirmation, the order status will be kept 'pending'. | fact |  | It describes the status after a successful payment-method change. |
| S19 | Modify payment | The original payment method will be refunded immediately if it is a gift card, otherwise in 5 to 7 business days. | fact |  | It describes the refund timing after a successful payment-method change. |
| S20 | Modify items | This action can only be called once, and will change the order status to 'pending (items modifed)', and the agent will not be able to modify or cancel the order anymore. | not_enforceable |  | The one-call limit cannot be decided from the permitted predicate sources, and the status change describes an outcome. |
| S21 | Modify items | So confirm all the details are right and be cautious before taking this action. | rule | 36, 37 | The item-change details must be listed and explicitly confirmed before the action. |
| S22 | Modify items | In particular, remember to remind the customer to confirm they have provided all items to be modified. | rule | 53 | The agent must remind the user to include all items before item modification. |
| S23 | Modify items | For a pending order, each item can be modified to an available new item of the same product but of different product option. | rule | 54 | Item modifications require available replacements of the same product with a different option. |
| S24 | Modify items | There cannot be any change of product types, e.g. modify shirt to shoe. | rule | 54 | The item-mapping rule prevents changing product types. |
| S25 | Modify items | The user must provide a payment method to pay or receive refund of the price difference. | rule | 55 | The user must choose the payment method for the price difference. |
| S26 | Modify items | If the user provides a gift card, it must have enough balance to cover the price difference. | rule | 56 | A gift card used for the price difference must have sufficient balance. |
| S27 | Return delivered order | An order can only be returned if its status is 'delivered', and you should check its status before taking the action. | rule | 57 | A return requires an earlier status check establishing that the order is delivered. |
| S28 | Return delivered order | The user needs to confirm the order id, the list of items to be returned, and a payment method to receive the refund. | rule | 42, 58 | The return details must be listed and the user must establish the order, items, and refund method. |
| S29 | Return delivered order | The refund must either go to the original payment method, or an existing gift card. | rule | 59 | The refund method must be the original payment method or an existing gift card. |
| S30 | Return delivered order | After user confirmation, the order status will be changed to 'return requested', and the user will receive an email regarding how to return items. | fact |  | It describes the result and follow-up email after a successful return request. |
| S31 | Exchange delivered order | An order can only be exchanged if its status is 'delivered', and you should check its status before taking the action. | rule | 60 | An exchange requires an earlier status check establishing that the order is delivered. |
| S32 | Exchange delivered order | In particular, remember to remind the customer to confirm they have provided all items to be exchanged. | rule | 61 | The agent must remind the user to include all items before exchange. |
| S33 | Exchange delivered order | For a delivered order, each item can be exchanged to an available new item of the same product but of different product option. | rule | 62 | Exchanges require available replacements of the same product with a different option. |
| S34 | Exchange delivered order | There cannot be any change of product types, e.g. modify shirt to shoe. | rule | 62 | The item-mapping rule prevents changing product types. |
| S35 | Exchange delivered order | The user must provide a payment method to pay or receive refund of the price difference. | rule | 63 | The user must choose the payment method for the price difference. |
| S36 | Exchange delivered order | If the user provides a gift card, it must have enough balance to cover the price difference. | rule | 64 | A gift card used for the price difference must have sufficient balance. |
| S37 | Exchange delivered order | After user confirmation, the order status will be changed to 'exchange requested', and the user will receive an email regarding how to return items. | fact |  | It describes the result and follow-up email after a successful exchange request. |
| S38 | Exchange delivered order | There is no need to place a new order. | fact |  | It describes that an exchange does not require a new order. |

## Validation

- repair rounds: 0
- remaining errors: none
- invalid rules dropped: none
- exact duplicates dropped: none
- declared but unused predicates: none
