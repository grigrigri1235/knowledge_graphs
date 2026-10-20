# TGR rules: retail (luna-dev, it4)

Flags: A+B. Rules: 61. Predicates: 26.

## Rules

| id | action(s) | logic | description | sentences |
|---|---|---|---|---|
| 1 | find_user_id_by_email | `find_user_id_by_email IMPLIES email_was_provided_by_user` | Use an email supplied by the user for the identity lookup. | S2 |
| 2 | find_user_id_by_email | `find_user_id_by_email IMPLIES NOT user_authenticated OR lookup_identifies_authenticated_user` | Do not use an email lookup to switch the conversation to a different user. | S5 |
| 3 | find_user_id_by_name_zip | `find_user_id_by_name_zip IMPLIES name_and_zip_were_provided_by_user` | Use the user's supplied first name, last name, and zip code for the identity lookup. | S2 |
| 4 | find_user_id_by_name_zip | `find_user_id_by_name_zip IMPLIES NOT user_authenticated OR lookup_identifies_authenticated_user` | Do not use a name-and-zip lookup to switch the conversation to a different user. | S5 |
| 5 | get_user_details | `get_user_details IMPLIES user_authenticated` | Authenticate the user before retrieving profile or order information. | S2, S3, S4 |
| 6 | get_user_details | `get_user_details IMPLIES pending_user_id_matches_authenticated_user` | Retrieve details only for the authenticated user. | S5 |
| 7 | get_order_details | `get_order_details IMPLIES user_authenticated` | Authenticate the user before retrieving order information. | S2, S3, S4 |
| 8 | get_order_details | `get_order_details IMPLIES pending_order_belongs_to_authenticated_user` | Retrieve order details only for an order belonging to the authenticated user. | S5 |
| 9 | get_product_details | `get_product_details IMPLIES user_authenticated` | Authenticate the user before retrieving product information for the user's request. | S2, S3, S4 |
| 10 | list_all_product_types | `list_all_product_types IMPLIES user_authenticated` | Authenticate the user before retrieving product information for the user's request. | S2, S3, S4 |
| 11 | respond | `respond IMPLIES NOT response_discloses_user_or_product_information OR user_authenticated` | Do not provide profile, order, or related-product information until the user has been authenticated. | S2, S3, S4 |
| 12 | respond | `respond IMPLIES NOT response_discloses_information_about_another_user` | Do not disclose information about another user. | S5 |
| 13 | transfer_to_human_agents | `transfer_to_human_agents IMPLIES request_cannot_be_handled_with_available_actions` | Transfer only when the request cannot be handled within the available actions. | S10 |
| 14 | cancel_pending_order | `cancel_pending_order IMPLIES user_authenticated` | Authenticate the user before cancelling an order. | S2, S3 |
| 15 | cancel_pending_order | `cancel_pending_order IMPLIES pending_order_belongs_to_authenticated_user` | Cancel only an order belonging to the authenticated user. | S5 |
| 16 | cancel_pending_order | `cancel_pending_order IMPLIES pending_order_status_was_checked_as_pending` | Check that the order is pending before cancelling it. | S11 |
| 17 | cancel_pending_order | `cancel_pending_order IMPLIES cancellation_order_id_and_reason_confirmed` | Require the user to confirm the order id and cancellation reason. | S12 |
| 18 | cancel_pending_order | `cancel_pending_order IMPLIES cancellation_reason_is_permitted` | Use only a permitted cancellation reason. | S12 |
| 19 | cancel_pending_order | `cancel_pending_order IMPLIES no_prior_item_modification_for_order` | Do not cancel an order after its items have been modified. | S20 |
| 20 | cancel_pending_order | `cancel_pending_order IMPLIES action_details_listed_and_yes_confirmed` | List the cancellation details and obtain the user's explicit yes before cancelling. | S6 |
| 21 | modify_pending_order_address | `modify_pending_order_address IMPLIES user_authenticated` | Authenticate the user before modifying an order. | S2, S3 |
| 22 | modify_pending_order_address | `modify_pending_order_address IMPLIES pending_order_belongs_to_authenticated_user` | Modify only an order belonging to the authenticated user. | S5 |
| 23 | modify_pending_order_address | `modify_pending_order_address IMPLIES pending_order_status_was_checked_as_pending` | Check that the order is pending before modifying it. | S14 |
| 24 | modify_pending_order_address | `modify_pending_order_address IMPLIES no_prior_item_modification_for_order` | Do not modify an order after its items have been modified. | S20 |
| 25 | modify_pending_order_address | `modify_pending_order_address IMPLIES action_details_listed_and_yes_confirmed` | List the address modification details and obtain the user's explicit yes before modifying the order. | S6 |
| 26 | modify_pending_order_payment | `modify_pending_order_payment IMPLIES user_authenticated` | Authenticate the user before modifying an order. | S2, S3 |
| 27 | modify_pending_order_payment | `modify_pending_order_payment IMPLIES pending_order_belongs_to_authenticated_user` | Modify only an order belonging to the authenticated user. | S5 |
| 28 | modify_pending_order_payment | `modify_pending_order_payment IMPLIES pending_order_status_was_checked_as_pending` | Check that the order is pending before modifying it. | S14 |
| 29 | modify_pending_order_payment | `modify_pending_order_payment IMPLIES no_prior_item_modification_for_order` | Do not modify an order after its items have been modified. | S20 |
| 30 | modify_pending_order_payment | `modify_pending_order_payment IMPLIES action_details_listed_and_yes_confirmed` | List the payment modification details and obtain the user's explicit yes before modifying the order. | S6 |
| 31 | modify_pending_order_payment | `modify_pending_order_payment IMPLIES payment_method_differs_from_original` | The selected payment method must differ from the original payment method. | S16 |
| 32 | modify_pending_order_payment | `modify_pending_order_payment IMPLIES payment_method_was_selected_by_user` | Use the single payment method selected by the user. | S16 |
| 33 | modify_pending_order_payment | `modify_pending_order_payment IMPLIES NOT selected_payment_method_is_gift_card OR gift_card_balance_covers_order_total` | A selected gift card must have enough balance to cover the order total. | S17 |
| 34 | modify_pending_order_items | `modify_pending_order_items IMPLIES user_authenticated` | Authenticate the user before modifying an order. | S2, S3 |
| 35 | modify_pending_order_items | `modify_pending_order_items IMPLIES pending_order_belongs_to_authenticated_user` | Modify only an order belonging to the authenticated user. | S5 |
| 36 | modify_pending_order_items | `modify_pending_order_items IMPLIES pending_order_status_was_checked_as_pending` | Check that the order is pending before modifying its items. | S14 |
| 37 | modify_pending_order_items | `modify_pending_order_items IMPLIES no_prior_item_modification_for_order` | Call the item-modification action no more than once for an order, and do not modify an order after its items have been modified. | S20 |
| 38 | modify_pending_order_items | `modify_pending_order_items IMPLIES action_details_listed_and_yes_confirmed` | List all item modification details and obtain the user's explicit yes before modifying the order. | S6, S21 |
| 39 | modify_pending_order_items | `modify_pending_order_items IMPLIES all_items_confirmation_reminder_sent` | Remind the user to confirm that they provided all items to be modified. | S22 |
| 40 | modify_pending_order_items | `modify_pending_order_items IMPLIES replacement_items_are_available` | Modify items only to available new items. | S23 |
| 41 | modify_pending_order_items | `modify_pending_order_items IMPLIES replacement_items_match_product_and_change_option` | Each replacement must be the same product with a different product option; do not change product types. | S23, S24 |
| 42 | modify_pending_order_items | `modify_pending_order_items IMPLIES price_difference_payment_method_was_provided_by_user` | Require the user to provide a payment method for the price difference. | S25 |
| 43 | modify_pending_order_items | `modify_pending_order_items IMPLIES NOT selected_payment_method_is_gift_card OR gift_card_balance_covers_price_difference` | A gift card provided for the price difference must have enough balance to cover it. | S26 |
| 44 | modify_user_address | `modify_user_address IMPLIES user_authenticated` | Authenticate the user before modifying their default address. | S2, S3 |
| 45 | modify_user_address | `modify_user_address IMPLIES pending_user_id_matches_authenticated_user` | Modify the default address only for the authenticated user. | S5 |
| 46 | modify_user_address | `modify_user_address IMPLIES action_details_listed_and_yes_confirmed` | List the address modification details and obtain the user's explicit yes before updating the address. | S6 |
| 47 | return_delivered_order_items | `return_delivered_order_items IMPLIES user_authenticated` | Authenticate the user before returning items. | S2, S3 |
| 48 | return_delivered_order_items | `return_delivered_order_items IMPLIES pending_order_belongs_to_authenticated_user` | Return items only from an order belonging to the authenticated user. | S5 |
| 49 | return_delivered_order_items | `return_delivered_order_items IMPLIES pending_order_status_was_checked_as_delivered` | Check that the order is delivered before returning items. | S27 |
| 50 | return_delivered_order_items | `return_delivered_order_items IMPLIES action_details_listed_and_yes_confirmed` | List the return details and obtain the user's explicit yes before requesting the return. | S6 |
| 51 | return_delivered_order_items | `return_delivered_order_items IMPLIES return_order_id_items_and_method_confirmed` | Require the user to confirm the order id, items to return, and refund payment method. | S28 |
| 52 | return_delivered_order_items | `return_delivered_order_items IMPLIES return_method_is_original_or_existing_gift_card` | Refund only to the original payment method or an existing gift card. | S29 |
| 53 | exchange_delivered_order_items | `exchange_delivered_order_items IMPLIES user_authenticated` | Authenticate the user before exchanging items. | S2, S3 |
| 54 | exchange_delivered_order_items | `exchange_delivered_order_items IMPLIES pending_order_belongs_to_authenticated_user` | Exchange items only from an order belonging to the authenticated user. | S5 |
| 55 | exchange_delivered_order_items | `exchange_delivered_order_items IMPLIES pending_order_status_was_checked_as_delivered` | Check that the order is delivered before exchanging items. | S31 |
| 56 | exchange_delivered_order_items | `exchange_delivered_order_items IMPLIES action_details_listed_and_yes_confirmed` | List all exchange details and obtain the user's explicit yes before requesting the exchange. | S6 |
| 57 | exchange_delivered_order_items | `exchange_delivered_order_items IMPLIES all_items_confirmation_reminder_sent` | Remind the user to confirm that they provided all items to be exchanged. | S32 |
| 58 | exchange_delivered_order_items | `exchange_delivered_order_items IMPLIES replacement_items_are_available` | Exchange items only to available new items. | S33 |
| 59 | exchange_delivered_order_items | `exchange_delivered_order_items IMPLIES replacement_items_match_product_and_change_option` | Each replacement must be the same product with a different product option; do not change product types. | S33, S34 |
| 60 | exchange_delivered_order_items | `exchange_delivered_order_items IMPLIES price_difference_payment_method_was_provided_by_user` | Require the user to provide a payment method for the price difference. | S35 |
| 61 | exchange_delivered_order_items | `exchange_delivered_order_items IMPLIES NOT selected_payment_method_is_gift_card OR gift_card_balance_covers_price_difference` | A gift card provided for the price difference must have enough balance to cover it. | S36 |

## Predicates

| name | description | source |
|---|---|---|
| action_details_listed_and_yes_confirmed | Before the pending action, the agent told the user the details matching that action's arguments, and the user explicitly replied yes to confirm proceeding with those details. | call_arguments, agent_messages, user_messages |
| all_items_confirmation_reminder_sent | Before the pending item modification or exchange, the agent reminded the user to confirm that they had provided all items to be modified or exchanged. | agent_messages |
| cancellation_order_id_and_reason_confirmed | The user explicitly confirmed the order_id and the cancellation reason in the pending cancellation arguments. | call_arguments, user_messages |
| cancellation_reason_is_permitted | The reason in the pending cancellation arguments is either 'no longer needed' or 'ordered by mistake'. | call_arguments |
| email_was_provided_by_user | The email in the pending lookup arguments was supplied by the user in the conversation. | call_arguments, user_messages |
| gift_card_balance_covers_order_total | Earlier tool outputs establish that the selected gift card has enough balance to cover the order total. | call_arguments, tool_outputs |
| gift_card_balance_covers_price_difference | Earlier tool outputs establish that the selected gift card has enough balance to cover the price difference for the pending item modification or exchange. | call_arguments, tool_outputs |
| lookup_identifies_authenticated_user | The person identified by the pending lookup arguments is the same person identified by the earlier successful user lookup. | call_arguments, tool_outputs, user_messages |
| name_and_zip_were_provided_by_user | The first name, last name, and zip code in the pending lookup arguments were supplied by the user in the conversation. | call_arguments, user_messages |
| no_prior_item_modification_for_order | No earlier call to modify_pending_order_items was made for the order_id in the pending action. | call_arguments, tool_outputs |
| payment_method_differs_from_original | The payment_method_id in the pending action differs from the original payment method for the order, as established by earlier tool outputs. | call_arguments, tool_outputs |
| payment_method_was_selected_by_user | The user selected the payment_method_id in the pending action. | call_arguments, user_messages |
| pending_order_belongs_to_authenticated_user | Earlier tool outputs establish that the order_id in the pending action arguments belongs to the user identified by the successful authentication lookup. | call_arguments, tool_outputs |
| pending_order_status_was_checked_as_delivered | An earlier get_order_details call for the order_id in the pending action returned status 'delivered'. | call_arguments, tool_outputs |
| pending_order_status_was_checked_as_pending | An earlier get_order_details call for the order_id in the pending action returned status 'pending'. | call_arguments, tool_outputs |
| pending_user_id_matches_authenticated_user | The user_id in the pending action arguments is the user id returned by the successful authentication lookup. | call_arguments, tool_outputs |
| price_difference_payment_method_was_provided_by_user | The user provided the payment_method_id in the pending action for paying or receiving the price difference. | call_arguments, user_messages |
| replacement_items_are_available | Earlier tool outputs establish that every new item in the pending action is available. | call_arguments, tool_outputs |
| replacement_items_match_product_and_change_option | For every paired item in the pending action, earlier tool outputs establish that the new item is the same product as the original item but has a different product option. | call_arguments, tool_outputs |
| request_cannot_be_handled_with_available_actions | The request is outside the policy's supported tasks or cannot be resolved using the available tools and information in the conversation. | user_messages, tool_outputs |
| response_discloses_information_about_another_user | The pending response provides information about a person other than the authenticated user. | call_arguments, tool_outputs, user_messages |
| response_discloses_user_or_product_information | The pending response provides information about a user's profile, orders, or related products. | call_arguments |
| return_method_is_original_or_existing_gift_card | Earlier tool outputs establish that the payment_method_id in the pending return action is either the order's original payment method or an existing gift card. | call_arguments, tool_outputs |
| return_order_id_items_and_method_confirmed | The user confirmed the order_id, all item_ids to be returned, and the payment_method_id in the pending return action. | call_arguments, user_messages |
| selected_payment_method_is_gift_card | The payment_method_id in the pending action identifies a gift card. | call_arguments, tool_outputs |
| user_authenticated | An earlier successful find_user_id_by_email or find_user_id_by_name_zip call located the current user's user id. | tool_outputs |

## Background facts for the judge

- [S1] As a retail agent, you can help users cancel or modify pending orders, return or exchange delivered orders, modify their default user address, or provide information about their own profile, orders, and related products.
- [S2] At the beginning of the conversation, you have to authenticate the user identity by locating their user id via email, or via name + zip code.
- [S3] This has to be done even when the user already provides the user id.
- [S11] An order can only be cancelled if its status is 'pending', and you should check its status before taking the action.
- [S12] The user needs to confirm the order id and the reason (either 'no longer needed' or 'ordered by mistake') for cancellation.
- [S14] An order can only be modified if its status is 'pending', and you should check its status before taking the action.
- [S16] The user can only choose a single payment method different from the original payment method.
- [S17] If the user wants the modify the payment method to gift card, it must have enough balance to cover the total amount.
- [S20] This action can only be called once, and will change the order status to 'pending (items modifed)', and the agent will not be able to modify or cancel the order anymore.
- [S23] For a pending order, each item can be modified to an available new item of the same product but of different product option.
- [S24] There cannot be any change of product types, e.g. modify shirt to shoe.
- [S26] If the user provides a gift card, it must have enough balance to cover the price difference.
- [S27] An order can only be returned if its status is 'delivered', and you should check its status before taking the action.
- [S29] The refund must either go to the original payment method, or an existing gift card.
- [S31] An order can only be exchanged if its status is 'delivered', and you should check its status before taking the action.
- [S33] For a delivered order, each item can be exchanged to an available new item of the same product but of different product option.
- [S34] There cannot be any change of product types, e.g. modify shirt to shoe.
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
| S1 | Retail agent policy | As a retail agent, you can help users cancel or modify pending orders, return or exchange delivered orders, modify their default user address, or provide information about their own profile, orders, and related products. | fact |  | Defines the supported scope used to assess whether a request can be handled. |
| S2 | Retail agent policy | At the beginning of the conversation, you have to authenticate the user identity by locating their user id via email, or via name + zip code. | rule | 1, 3, 5, 7, 9, 10, 14, 21, 26, 34, 44, 47, 53 | Lookup inputs and authenticated access are required before user service actions. |
| S3 | Retail agent policy | This has to be done even when the user already provides the user id. | rule | 5, 7, 9, 10, 14, 21, 26, 34, 44, 47, 53 | User-supplied ids do not replace the required identity lookup. |
| S4 | Retail agent policy | Once the user has been authenticated, you can provide the user with information about order, product, profile information, e.g. help the user look up order id. | rule | 5, 7, 9, 10, 11 | Information access and disclosure are restricted until authentication. |
| S5 | Retail agent policy | You can only help one user per conversation (but you can handle multiple requests from the same user), and must deny any requests for tasks related to any other user. | rule | 2, 4, 6, 8, 12, 15, 22, 27, 35, 45, 48, 54 | Rules restrict lookups, actions, and disclosures to the authenticated user. |
| S6 | Retail agent policy | Before taking consequential actions that update the database (cancel, modify, return, exchange), you have to list the action detail and obtain explicit user confirmation (yes) to proceed. | rule | 20, 25, 30, 38, 46, 50, 56 | Each consequential action requires listed details and an explicit yes. |
| S7 | Retail agent policy | You should not make up any information or knowledge or procedures not provided from the user or the tools, or give subjective recommendations or comments. | not_enforceable |  | General truthfulness, grounding, and subjectivity requirements are not restrictions on a single action. |
| S8 | Retail agent policy | You should at most make one tool call at a time, and if you take a tool call, you should not respond to the user at the same time. | not_enforceable |  | Combining tool calls and messages cannot be checked one action at a time. |
| S9 | Retail agent policy | If you respond to the user, you should not make a tool call. | not_enforceable |  | Combining a response with a tool call cannot be checked one action at a time. |
| S10 | Retail agent policy | You should transfer the user to a human agent if and only if the request cannot be handled within the scope of your actions. | rule | 13 | The rule restricts transfer to requests the available actions cannot handle. |
| S11 | Cancel pending order | An order can only be cancelled if its status is 'pending', and you should check its status before taking the action. | rule | 16 | Cancellation requires a prior status check showing pending. |
| S12 | Cancel pending order | The user needs to confirm the order id and the reason (either 'no longer needed' or 'ordered by mistake') for cancellation. | rule | 17, 18 | The order id and permitted cancellation reason must be confirmed. |
| S13 | Cancel pending order | After user confirmation, the order status will be changed to 'cancelled', and the total will be refunded via the original payment method immediately if it is gift card, otherwise in 5 to 7 business days. | fact |  | Describes the cancellation result and refund timing. |
| S14 | Modify pending order | An order can only be modified if its status is 'pending', and you should check its status before taking the action. | rule | 23, 28, 36 | Pending-order modifications require a prior status check showing pending. |
| S15 | Modify pending order | For a pending order, you can take actions to modify its shipping address, payment method, or product item options, but nothing else. | fact |  | The available modification tools already limit the supported modification types. |
| S16 | Modify payment | The user can only choose a single payment method different from the original payment method. | rule | 31, 32 | The selected payment method must be user-selected and differ from the original. |
| S17 | Modify payment | If the user wants the modify the payment method to gift card, it must have enough balance to cover the total amount. | rule | 33 | A gift card used for payment must cover the order total. |
| S18 | Modify payment | After user confirmation, the order status will be kept 'pending'. | fact |  | Describes the status after payment modification. |
| S19 | Modify payment | The original payment method will be refunded immediately if it is a gift card, otherwise in 5 to 7 business days. | fact |  | Describes the refund timing for the original payment method. |
| S20 | Modify items | This action can only be called once, and will change the order status to 'pending (items modifed)', and the agent will not be able to modify or cancel the order anymore. | rule | 19, 24, 29, 37 | The item action is limited to one call, after which the order cannot be modified or cancelled. |
| S21 | Modify items | So confirm all the details are right and be cautious before taking this action. | rule | 38 | The action requires details to be listed and explicitly confirmed before proceeding. |
| S22 | Modify items | In particular, remember to remind the customer to confirm they have provided all items to be modified. | rule | 39 | The agent must remind the user to confirm all items before the action. |
| S23 | Modify items | For a pending order, each item can be modified to an available new item of the same product but of different product option. | rule | 40, 41 | Replacement items must be available and match the product with a different option. |
| S24 | Modify items | There cannot be any change of product types, e.g. modify shirt to shoe. | rule | 41 | The replacement must not change the product type. |
| S25 | Modify items | The user must provide a payment method to pay or receive refund of the price difference. | rule | 42 | The user must provide the price-difference payment method. |
| S26 | Modify items | If the user provides a gift card, it must have enough balance to cover the price difference. | rule | 43 | A gift card used for the price difference must cover it. |
| S27 | Return delivered order | An order can only be returned if its status is 'delivered', and you should check its status before taking the action. | rule | 49 | A return requires a prior status check showing delivered. |
| S28 | Return delivered order | The user needs to confirm the order id, the list of items to be returned, and a payment method to receive the refund. | rule | 51 | The user must confirm the order, returned items, and refund method. |
| S29 | Return delivered order | The refund must either go to the original payment method, or an existing gift card. | rule | 52 | The refund destination must be the original method or an existing gift card. |
| S30 | Return delivered order | After user confirmation, the order status will be changed to 'return requested', and the user will receive an email regarding how to return items. | fact |  | Describes the return result and follow-up email. |
| S31 | Exchange delivered order | An order can only be exchanged if its status is 'delivered', and you should check its status before taking the action. | rule | 55 | An exchange requires a prior status check showing delivered. |
| S32 | Exchange delivered order | In particular, remember to remind the customer to confirm they have provided all items to be exchanged. | rule | 57 | The agent must remind the user to confirm all items before the exchange. |
| S33 | Exchange delivered order | For a delivered order, each item can be exchanged to an available new item of the same product but of different product option. | rule | 58, 59 | Exchange items must be available and match the product with a different option. |
| S34 | Exchange delivered order | There cannot be any change of product types, e.g. modify shirt to shoe. | rule | 59 | The exchange must not change the product type. |
| S35 | Exchange delivered order | The user must provide a payment method to pay or receive refund of the price difference. | rule | 60 | The user must provide the price-difference payment method. |
| S36 | Exchange delivered order | If the user provides a gift card, it must have enough balance to cover the price difference. | rule | 61 | A gift card used for the price difference must cover it. |
| S37 | Exchange delivered order | After user confirmation, the order status will be changed to 'exchange requested', and the user will receive an email regarding how to return items. | fact |  | Describes the exchange result and follow-up email. |
| S38 | Exchange delivered order | There is no need to place a new order. | fact |  | States that an exchange does not require a new order. |

## Validation

- repair rounds: 0
- remaining errors: none
- invalid rules dropped: none
- exact duplicates dropped: none
- declared but unused predicates: none
