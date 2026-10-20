# E2 worksheet — retail — output/auto_aspm/retail/v1

Auto rules: 108

## RET-GEN-01a
- gold quote: "At the beginning of the conversation, you have to authenticate the user identity by locating their user id via email, or via name + zip code."
- gold reading: Before anything else, the agent authenticates the user via find_user_id_by_email or find_user_id_by_name_zip.
- GOLD RET-R001: The agent must authenticate the user by locating their user id via email (find_user_id_by_email) or via name and zip code (find_user_id_by_name_zip) before any other tool call or any disclosure of profile, order, or product information, even if the user has already provided a user id.
- aligned auto clauses: S0-C02
  - SRC S0-C02-R1 [cancel_pending_order,exchange_delivered_order_items,find_user_id_by_email,find_user_id_by_name_zip,get_order_details,get_user_details,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must]: The agent must authenticate the user identity at the beginning of the conversation by locating the user id via email, or via name + zip code.
  - SRC S0-C04-R1 [cancel_pending_order,exchange_delivered_order_items,get_order_details,get_user_details,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,respond_to_user,return_delivered_order_items; must_not]: The agent must not provide information about orders unless the user has been authenticated.
  - SRC S0-C04-R2 [get_product_details,list_all_product_types,respond_to_user; must_not]: The agent must not provide information about products unless the user has been authenticated.
  - SRC S0-C04-R3 [find_user_id_by_email,find_user_id_by_name_zip,get_order_details,get_user_details; must_not]: The agent must not provide profile information unless the user has been authenticated.
  - SIM S6-C03-R1 [cancel_pending_order,exchange_delivered_order_items,get_order_details,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must]: The agent must obtain the user's confirmation of the order id.
  - SIM S2-C05-R4 [cancel_pending_order; must]: The agent must require the user to confirm the order id before cancelling.

## RET-GEN-01b
- gold quote: "This has to be done even when the user already provides the user id."
- gold reading: A user-supplied user id does not replace authentication.
- GOLD RET-R001: The agent must authenticate the user by locating their user id via email (find_user_id_by_email) or via name and zip code (find_user_id_by_name_zip) before any other tool call or any disclosure of profile, order, or product information, even if the user has already provided a user id.
- aligned auto clauses: S0-C03
  - SRC S0-C02-R1 [cancel_pending_order,exchange_delivered_order_items,find_user_id_by_email,find_user_id_by_name_zip,get_order_details,get_user_details,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must]: The agent must authenticate the user identity at the beginning of the conversation by locating the user id via email, or via name + zip code.
  - SRC S0-C04-R1 [cancel_pending_order,exchange_delivered_order_items,get_order_details,get_user_details,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,respond_to_user,return_delivered_order_items; must_not]: The agent must not provide information about orders unless the user has been authenticated.
  - SRC S0-C04-R2 [get_product_details,list_all_product_types,respond_to_user; must_not]: The agent must not provide information about products unless the user has been authenticated.
  - SRC S0-C04-R3 [find_user_id_by_email,find_user_id_by_name_zip,get_order_details,get_user_details; must_not]: The agent must not provide profile information unless the user has been authenticated.
  - SIM S6-C03-R1 [cancel_pending_order,exchange_delivered_order_items,get_order_details,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must]: The agent must obtain the user's confirmation of the order id.
  - SIM S2-C05-R4 [cancel_pending_order; must]: The agent must require the user to confirm the order id before cancelling.

## RET-GEN-02
- gold quote: "Once the user has been authenticated, you can provide the user with information about order, product, profile information, e.g. help the user look up order id."
- gold reading: Information about orders/products/profile may be provided only after authentication.
- GOLD RET-R001: The agent must authenticate the user by locating their user id via email (find_user_id_by_email) or via name and zip code (find_user_id_by_name_zip) before any other tool call or any disclosure of profile, order, or product information, even if the user has already provided a user id.
- aligned auto clauses: S0-C04
  - SRC S0-C04-R1 [cancel_pending_order,exchange_delivered_order_items,get_order_details,get_user_details,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,respond_to_user,return_delivered_order_items; must_not]: The agent must not provide information about orders unless the user has been authenticated.
  - SRC S0-C04-R2 [get_product_details,list_all_product_types,respond_to_user; must_not]: The agent must not provide information about products unless the user has been authenticated.
  - SRC S0-C04-R3 [find_user_id_by_email,find_user_id_by_name_zip,get_order_details,get_user_details; must_not]: The agent must not provide profile information unless the user has been authenticated.
  - SIM S0-C02-R1 [cancel_pending_order,exchange_delivered_order_items,find_user_id_by_email,find_user_id_by_name_zip,get_order_details,get_user_details,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must]: The agent must authenticate the user identity at the beginning of the conversation by locating the user id via email, or via name + zip code.
  - SIM S6-C03-R1 [cancel_pending_order,exchange_delivered_order_items,get_order_details,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must]: The agent must obtain the user's confirmation of the order id.
  - SIM S0-C01-R4 [find_user_id_by_email,find_user_id_by_name_zip,get_order_details,get_product_details,get_user_details,list_all_product_types; may]: The agent must provide information about their own profile, orders, and related products.

## RET-GEN-03a
- gold quote: "You can only help one user per conversation (but you can handle multiple requests from the same user)"
- gold reading: All actions concern the single authenticated user.
- GOLD RET-R002: The agent must only act on the authenticated user's own account and orders: every user id and order passed to a tool must belong to the user authenticated in this conversation.
- aligned auto clauses: S0-C05
  - SRC S0-C05-R1 [cancel_pending_order,exchange_delivered_order_items,find_user_id_by_email,find_user_id_by_name_zip,get_order_details,get_user_details,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must_not]: The agent must not provide assistance to any user other than the one currently participating in the conversation.
  - SRC S0-C05-R2 [cancel_pending_order,exchange_delivered_order_items,find_user_id_by_email,find_user_id_by_name_zip,get_order_details,get_user_details,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,modify_user_address,return_delivered_order_items; must]: The agent must deny requests for tasks related to any other user.
  - SIM S0-C04-R1 [cancel_pending_order,exchange_delivered_order_items,get_order_details,get_user_details,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,respond_to_user,return_delivered_order_items; must_not]: The agent must not provide information about orders unless the user has been authenticated.
  - SIM S0-C04-R3 [find_user_id_by_email,find_user_id_by_name_zip,get_order_details,get_user_details; must_not]: The agent must not provide profile information unless the user has been authenticated.
  - SIM S0-C04-R2 [get_product_details,list_all_product_types,respond_to_user; must_not]: The agent must not provide information about products unless the user has been authenticated.

## RET-GEN-03b
- gold quote: "and must deny any requests for tasks related to any other user."
- gold reading: Requests about other users are denied.
- GOLD RET-R003: The agent must deny any request for tasks related to a user other than the authenticated user.
- aligned auto clauses: S0-C05
  - SRC S0-C05-R1 [cancel_pending_order,exchange_delivered_order_items,find_user_id_by_email,find_user_id_by_name_zip,get_order_details,get_user_details,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must_not]: The agent must not provide assistance to any user other than the one currently participating in the conversation.
  - SRC S0-C05-R2 [cancel_pending_order,exchange_delivered_order_items,find_user_id_by_email,find_user_id_by_name_zip,get_order_details,get_user_details,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,modify_user_address,return_delivered_order_items; must]: The agent must deny requests for tasks related to any other user.
  - SIM S0-C04-R3 [find_user_id_by_email,find_user_id_by_name_zip,get_order_details,get_user_details; must_not]: The agent must not provide profile information unless the user has been authenticated.
  - SIM S0-C04-R2 [get_product_details,list_all_product_types,respond_to_user; must_not]: The agent must not provide information about products unless the user has been authenticated.

## RET-GEN-04a
- gold quote: "Before taking consequential actions that update the database (cancel, modify, return, exchange), you have to list the action detail"
- gold reading: Before any DB-updating action, the agent lists the action details.
- GOLD RET-R004: The agent must list the action details to the user before calling any tool that updates the database (cancel, modify, return, or exchange).
- aligned auto clauses: S0-C06
  - SRC S0-C06-R1 [cancel_pending_order; must]: The agent must list the cancellation details and obtain explicit user confirmation (yes) to proceed before cancelling a pending order.
  - SRC S0-C06-R2 [modify_pending_order_address; must]: The agent must list the modification details and obtain explicit user confirmation (yes) to proceed before modifying the shipping address of a pending order.
  - SRC S0-C06-R3 [cancel_pending_order,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment; must]: The agent must list the modification details and obtain explicit user confirmation (yes) to proceed before modifying items in a pending order.
  - SRC S0-C06-R4 [modify_pending_order_payment; must]: The agent must list the modification details and obtain explicit user confirmation (yes) to proceed before modifying the payment method of a pending order.
  - SRC S0-C06-R5 [exchange_delivered_order_items,return_delivered_order_items; must]: The agent must list the return details and obtain explicit user confirmation (yes) to proceed before returning items from a delivered order.
  - SRC S0-C06-R6 [exchange_delivered_order_items; must]: The agent must list the exchange details and obtain explicit user confirmation (yes) to proceed before exchanging delivered order items.
  - SIM S2-C05-R6 [cancel_pending_order; must]: The agent must call the cancellation tool to change the order status to 'cancelled' and process the refund when the user has confirmed.
  - SIM S0-C01-R1 [cancel_pending_order,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment; may]: The agent must help users cancel or modify pending orders.
  - SIM S0-C01-R3 [modify_user_address; may]: The agent must help users modify their default user address.

## RET-GEN-04b
- gold quote: "obtain explicit user confirmation (yes) to proceed."
- gold reading: Before any DB-updating action, explicit 'yes' from the user.
- GOLD RET-R005: The agent must obtain an explicit 'yes' from the user, given after the action details were listed, before calling any tool that updates the database.
- aligned auto clauses: S0-C06
  - SRC S0-C06-R1 [cancel_pending_order; must]: The agent must list the cancellation details and obtain explicit user confirmation (yes) to proceed before cancelling a pending order.
  - SRC S0-C06-R2 [modify_pending_order_address; must]: The agent must list the modification details and obtain explicit user confirmation (yes) to proceed before modifying the shipping address of a pending order.
  - SRC S0-C06-R3 [cancel_pending_order,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment; must]: The agent must list the modification details and obtain explicit user confirmation (yes) to proceed before modifying items in a pending order.
  - SRC S0-C06-R4 [modify_pending_order_payment; must]: The agent must list the modification details and obtain explicit user confirmation (yes) to proceed before modifying the payment method of a pending order.
  - SRC S0-C06-R5 [exchange_delivered_order_items,return_delivered_order_items; must]: The agent must list the return details and obtain explicit user confirmation (yes) to proceed before returning items from a delivered order.
  - SRC S0-C06-R6 [exchange_delivered_order_items; must]: The agent must list the exchange details and obtain explicit user confirmation (yes) to proceed before exchanging delivered order items.
  - SIM S5-C06-R6 [cancel_pending_order,exchange_delivered_order_items,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,modify_user_address,return_delivered_order_items; must]: The agent must obtain explicit user confirmation (yes/no) before proceeding with the modification.

## RET-GEN-05a
- gold quote: "You should not make up any information or knowledge or procedures not provided from the user or the tools"
- gold reading: The agent must not make up information/knowledge/procedures.
- GOLD RET-R006: The agent must not make up information, knowledge, or procedures that were not provided by the user or by the tools.
- aligned auto clauses: S0-C07
  - SRC S0-C07-R1 [respond_to_user; must_not]: The agent must not make up any information not provided by the user or the tools.
  - SRC S0-C07-R2 [respond_to_user,transfer_to_human_agents; must_not]: The agent must not make up any knowledge not provided by the user or the tools.
  - SRC S0-C07-R3 [respond_to_user; must_not]: The agent must not make up any procedures not provided by the user or the tools.
  - SRC S0-C07-R4 [respond_to_user; must_not]: The agent must not give subjective recommendations or comments.

## RET-GEN-05b
- gold quote: "or give subjective recommendations or comments."
- gold reading: The agent must not give subjective recommendations or comments.
- GOLD RET-R007: The agent must not give subjective recommendations or comments.
- aligned auto clauses: S0-C07
  - SRC S0-C07-R1 [respond_to_user; must_not]: The agent must not make up any information not provided by the user or the tools.
  - SRC S0-C07-R2 [respond_to_user,transfer_to_human_agents; must_not]: The agent must not make up any knowledge not provided by the user or the tools.
  - SRC S0-C07-R3 [respond_to_user; must_not]: The agent must not make up any procedures not provided by the user or the tools.
  - SRC S0-C07-R4 [respond_to_user; must_not]: The agent must not give subjective recommendations or comments.
  - SIM S0-C05-R1 [cancel_pending_order,exchange_delivered_order_items,find_user_id_by_email,find_user_id_by_name_zip,get_order_details,get_user_details,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must_not]: The agent must not provide assistance to any user other than the one currently participating in the conversation.
  - SIM S0-C09-R1 [calculate,cancel_pending_order,exchange_delivered_order_items,find_user_id_by_email,find_user_id_by_name_zip,get_order_details,get_product_details,get_user_details,list_all_product_types,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,modify_user_address,return_delivered_order_items,think,transfer_to_human_agents; must_not]: The agent must not call any tool while responding to the user.

## RET-GEN-06a
- gold quote: "You should at most make one tool call at a time"
- gold reading: At most one tool call per agent turn.
- GOLD RET-R008: The agent must make at most one tool call per turn.
- aligned auto clauses: S0-C08
  - SRC S0-C08-R1 [calculate,cancel_pending_order,exchange_delivered_order_items,find_user_id_by_email,find_user_id_by_name_zip,get_order_details,get_product_details,get_user_details,list_all_product_types,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,modify_user_address,return_delivered_order_items,transfer_to_human_agents; must_not]: The agent must not initiate a second tool call while a first tool call is in progress.
  - SRC S0-C08-R2 [cancel_pending_order,exchange_delivered_order_items,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,respond_to_user,return_delivered_order_items,transfer_to_human_agents; must_not]: The agent must not respond to the user while a tool call is in progress.
  - SIM S0-C09-R1 [calculate,cancel_pending_order,exchange_delivered_order_items,find_user_id_by_email,find_user_id_by_name_zip,get_order_details,get_product_details,get_user_details,list_all_product_types,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,modify_user_address,return_delivered_order_items,think,transfer_to_human_agents; must_not]: The agent must not call any tool while responding to the user.
  - SIM S1-C13-R2 [exchange_delivered_order_items,modify_pending_order_items,return_delivered_order_items; must_not]: The agent must not perform an order-item change tool call more than once.

## RET-GEN-06b
- gold quote: "if you take a tool call, you should not respond to the user at the same time."
- gold reading: No user-facing message in a tool-call turn.
- GOLD RET-R009: The agent must not respond to the user and make a tool call in the same turn.
- aligned auto clauses: S0-C08
  - SRC S0-C08-R1 [calculate,cancel_pending_order,exchange_delivered_order_items,find_user_id_by_email,find_user_id_by_name_zip,get_order_details,get_product_details,get_user_details,list_all_product_types,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,modify_user_address,return_delivered_order_items,transfer_to_human_agents; must_not]: The agent must not initiate a second tool call while a first tool call is in progress.
  - SRC S0-C08-R2 [cancel_pending_order,exchange_delivered_order_items,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,respond_to_user,return_delivered_order_items,transfer_to_human_agents; must_not]: The agent must not respond to the user while a tool call is in progress.
  - SIM S0-C09-R1 [calculate,cancel_pending_order,exchange_delivered_order_items,find_user_id_by_email,find_user_id_by_name_zip,get_order_details,get_product_details,get_user_details,list_all_product_types,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,modify_user_address,return_delivered_order_items,think,transfer_to_human_agents; must_not]: The agent must not call any tool while responding to the user.

## RET-GEN-06c
- gold quote: "If you respond to the user, you should not make a tool call."
- gold reading: No tool call in a user-facing-message turn.
- GOLD RET-R009: The agent must not respond to the user and make a tool call in the same turn.
- aligned auto clauses: S0-C09
  - SRC S0-C09-R1 [calculate,cancel_pending_order,exchange_delivered_order_items,find_user_id_by_email,find_user_id_by_name_zip,get_order_details,get_product_details,get_user_details,list_all_product_types,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,modify_user_address,return_delivered_order_items,think,transfer_to_human_agents; must_not]: The agent must not call any tool while responding to the user.
  - SIM S0-C08-R2 [cancel_pending_order,exchange_delivered_order_items,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,respond_to_user,return_delivered_order_items,transfer_to_human_agents; must_not]: The agent must not respond to the user while a tool call is in progress.
  - SIM S0-C08-R1 [calculate,cancel_pending_order,exchange_delivered_order_items,find_user_id_by_email,find_user_id_by_name_zip,get_order_details,get_product_details,get_user_details,list_all_product_types,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,modify_user_address,return_delivered_order_items,transfer_to_human_agents; must_not]: The agent must not initiate a second tool call while a first tool call is in progress.

## RET-GEN-07a
- gold quote: "You should transfer the user to a human agent if and only if the request cannot be handled within the scope of your actions."
- gold reading: ONLY-IF direction: no transfer when the request is handleable.
- GOLD RET-R010: The agent must not transfer the user to a human agent unless the request cannot be handled within the scope of the agent's actions or the user explicitly asks for a human agent.
- aligned auto clauses: S0-C10
  - SRC S0-C10-R1 [transfer_to_human_agents; if_and_only_if]: The agent must transfer to a human agent if the request cannot be handled within the scope of your actions.
  - SRC S0-C10-R2 [transfer_to_human_agents; if_and_only_if]: The agent must not transfer to a human agent if the request can be handled within the scope of your actions.
  - SIM S0-C09-R1 [calculate,cancel_pending_order,exchange_delivered_order_items,find_user_id_by_email,find_user_id_by_name_zip,get_order_details,get_product_details,get_user_details,list_all_product_types,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,modify_user_address,return_delivered_order_items,think,transfer_to_human_agents; must_not]: The agent must not call any tool while responding to the user.

## RET-GEN-07b
- gold quote: "You should transfer the user to a human agent if and only if the request cannot be handled within the scope of your actions."
- gold reading: IF direction: transfer when the request cannot be handled within scope.
- GOLD RET-R011: The agent must transfer the user to a human agent when the request cannot be handled within the scope of the agent's actions.
- aligned auto clauses: S0-C10
  - SRC S0-C10-R1 [transfer_to_human_agents; if_and_only_if]: The agent must transfer to a human agent if the request cannot be handled within the scope of your actions.
  - SRC S0-C10-R2 [transfer_to_human_agents; if_and_only_if]: The agent must not transfer to a human agent if the request can be handled within the scope of your actions.
  - SIM S0-C09-R1 [calculate,cancel_pending_order,exchange_delivered_order_items,find_user_id_by_email,find_user_id_by_name_zip,get_order_details,get_product_details,get_user_details,list_all_product_types,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,modify_user_address,return_delivered_order_items,think,transfer_to_human_agents; must_not]: The agent must not call any tool while responding to the user.

## RET-DOM-04b
- gold quote: "They have no relations and should not be confused."
- gold reading: The agent must not confuse product ids with item ids.
- GOLD RET-R012: The agent must not confuse product ids with item ids: item ids passed to order tools must be item ids, and get_product_details must be called with a product id.
- aligned auto clauses: S1-C09
  - SIM S6-C03-R1 [cancel_pending_order,exchange_delivered_order_items,get_order_details,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must]: The agent must obtain the user's confirmation of the order id.
  - SIM S2-C05-R4 [cancel_pending_order; must]: The agent must require the user to confirm the order id before cancelling.
  - SIM S5-C07-R1 [modify_pending_order_items; must_not]: The agent must not change the product type of any item.

## RET-DOM-05b
- gold quote: "Generally, you can only take action on pending or delivered orders."
- gold reading: Write actions only on pending or delivered orders.
- GOLD RET-R013: The agent must not cancel or modify (address, payment method, or items) an order unless its status is exactly 'pending'.
- GOLD RET-R014: The agent must not return or exchange items of an order unless its status is exactly 'delivered'.
- aligned auto clauses: S1-C11
  - SIM S3-C04-R2 [modify_pending_order_payment; must_not]: The agent must not modify the payment method of an order unless its status is 'pending'.
  - SIM S7-C02-R1 [exchange_delivered_order_items; must]: The agent must exchange an order only if its status is 'delivered'.
  - SIM S3-C01-R3 [cancel_pending_order,modify_pending_order_items; must_not]: The agent must not modify any attribute of a pending order other than the shipping address, the payment method, or the product item options.

## RET-DOM-06a
- gold quote: "Exchange or modify order tools can only be called once."
- gold reading: exchange_delivered_order_items / modify_pending_order_items at most once per order.
- GOLD RET-R016: The agent must call modify_pending_order_items at most once per order.
- GOLD RET-R017: The agent must call exchange_delivered_order_items at most once per order.
- aligned auto clauses: S1-C12
  - SRC S1-C12-R1 [exchange_delivered_order_items; must_not]: The agent must not call the operation to exchange items in a delivered order more than once.
  - SRC S1-C12-R3 [modify_pending_order_address; must_not]: The agent must not modify the shipping address of a pending order more than once.
  - SRC S1-C12-R4 [modify_pending_order_payment; must_not]: The agent must not modify the payment method of a pending order more than once.
  - SRC S1-C13-R1 [cancel_pending_order,exchange_delivered_order_items,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must]: The agent must ensure that all items to be changed are collected into a list before making a tool call that changes an order.
  - SRC S1-C13-R2 [exchange_delivered_order_items,modify_pending_order_items,return_delivered_order_items; must_not]: The agent must not perform an order-item change tool call more than once.
  - SRC S5-C06-R2 [modify_pending_order_items; must_not]: The agent must not call modify_pending_order_items more than once for a pending order.
  - SIM S7-C09-R1 [exchange_delivered_order_items; must_not]: The agent must not require the user to place a new order to exchange items from a delivered order.

## RET-DOM-06b
- gold quote: "Be sure that all items to be changed are collected into a list before making the tool call!!!"
- gold reading: All items to change go into the single call.
- GOLD RET-R018: The agent must collect every item the user wants to change into the item list of a single modify-items or exchange call.
- aligned auto clauses: S1-C13
  - SRC S1-C13-R1 [cancel_pending_order,exchange_delivered_order_items,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must]: The agent must ensure that all items to be changed are collected into a list before making a tool call that changes an order.
  - SRC S1-C13-R2 [exchange_delivered_order_items,modify_pending_order_items,return_delivered_order_items; must_not]: The agent must not perform an order-item change tool call more than once.
  - SIM S5-C02-R6 [exchange_delivered_order_items,modify_pending_order_items; must]: The agent must modify each item to an available new item of the same product but of different product option
  - SIM S5-C06-R7 [exchange_delivered_order_items,modify_pending_order_items; must_not]: The agent must not modify an item if there is no available new item of the same product with a different option.
  - SIM S5-C07-R1 [modify_pending_order_items; must_not]: The agent must not change the product type of any item.

## RET-CAN-01a
- gold quote: "An order can only be cancelled if its status is 'pending'"
- gold reading: Cancel only if status == 'pending'.
- GOLD RET-R013: The agent must not cancel or modify (address, payment method, or items) an order unless its status is exactly 'pending'.
- aligned auto clauses: S2-C01
  - SRC S2-C01-R1 [cancel_pending_order; must_not]: The agent must not cancel an order unless the order status is 'pending'.
  - SRC S2-C03-R1 [cancel_pending_order; must]: The agent must obtain explicit user confirmation of the order id before cancelling the order, and the cancellation may be performed only if the order status is 'pending'.
  - SRC S2-C05-R2 [cancel_pending_order; must_not]: The agent must not cancel the order unless its status is 'pending'.
  - SIM S3-C04-R2 [modify_pending_order_payment; must_not]: The agent must not modify the payment method of an order unless its status is 'pending'.
  - SIM S3-C01-R3 [cancel_pending_order,modify_pending_order_items; must_not]: The agent must not modify any attribute of a pending order other than the shipping address, the payment method, or the product item options.

## RET-CAN-01b
- gold quote: "and you should check its status before taking the action."
- gold reading: Check the status (get_order_details) before cancelling.
- GOLD RET-R015: The agent must look up the order's current status (get_order_details) before cancelling, modifying, returning, or exchanging it.
- aligned auto clauses: S2-C02
  - SRC S2-C01-R1 [cancel_pending_order; must_not]: The agent must not cancel an order unless the order status is 'pending'.
  - SRC S2-C02-R1 [cancel_pending_order; must]: The agent must check the order status before taking the cancellation action.
  - SRC S2-C05-R1 [cancel_pending_order; must]: The agent must verify the current order status by retrieving the order details before attempting cancellation.
  - SIM S2-C03-R1 [cancel_pending_order; must]: The agent must obtain explicit user confirmation of the order id before cancelling the order, and the cancellation may be performed only if the order status is 'pending'.
  - SIM S0-C06-R1 [cancel_pending_order; must]: The agent must list the cancellation details and obtain explicit user confirmation (yes) to proceed before cancelling a pending order.

## RET-CAN-02a
- gold quote: "The user needs to confirm the order id and the reason"
- gold reading: Before cancelling, the user confirms order id and reason.
- GOLD RET-R020: Before cancelling an order, the agent must have the user confirm the order id and the cancellation reason.
- aligned auto clauses: S2-C03
  - SRC S2-C03-R1 [cancel_pending_order; must]: The agent must obtain explicit user confirmation of the order id before cancelling the order, and the cancellation may be performed only if the order status is 'pending'.
  - SRC S2-C05-R4 [cancel_pending_order; must]: The agent must require the user to confirm the order id before cancelling.
  - SIM S2-C04-R1 [cancel_pending_order; must]: The agent must confirm the cancellation reason as either 'no longer needed' or 'ordered by mistake'.

## RET-CAN-02b
- gold quote: "(either 'no longer needed' or 'ordered by mistake') for cancellation."
- gold reading: Reason ∈ {'no longer needed', 'ordered by mistake'}.
- GOLD RET-R021: The agent must only cancel an order with the reason 'no longer needed' or 'ordered by mistake'.
- aligned auto clauses: S2-C04
  - SRC S2-C04-R1 [cancel_pending_order; must]: The agent must confirm the cancellation reason as either 'no longer needed' or 'ordered by mistake'.
  - SRC S2-C05-R5 [cancel_pending_order; must]: The agent must require explicit confirmation of the cancellation reason from the user, either 'no longer needed' or 'ordered by mistake'.
  - SIM S5-C03-R2 [cancel_pending_order; must_not]: The agent must not cancel the order anymore.

## RET-MOD-01a
- gold quote: "An order can only be modified if its status is 'pending'"
- gold reading: Modify only if status == 'pending'.
- GOLD RET-R013: The agent must not cancel or modify (address, payment method, or items) an order unless its status is exactly 'pending'.
- aligned auto clauses: S3-C01
  - SRC S3-C01-R2 [cancel_pending_order,exchange_delivered_order_items,get_order_details,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must]: The agent must check the order's status before taking any modification action.
  - SRC S3-C01-R3 [cancel_pending_order,modify_pending_order_items; must_not]: The agent must not modify any attribute of a pending order other than the shipping address, the payment method, or the product item options.
  - SRC S3-C02-R1 [cancel_pending_order,exchange_delivered_order_items,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must]: The agent must check the status of the order before taking any modification action on that order.
  - SRC S3-C02-R2 [cancel_pending_order,exchange_delivered_order_items,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must]: The agent must modify the order only if its status is 'pending'.
  - SRC S3-C03-R1 [modify_pending_order_address; must_not]: The agent must not modify the shipping address of an order unless its status is 'pending'.
  - SRC S3-C04-R2 [modify_pending_order_payment; must_not]: The agent must not modify the payment method of an order unless its status is 'pending'.
  - SRC S3-C05-R1 [cancel_pending_order,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment; must]: The agent must verify the order's status before taking any modification action on a pending order.
  - SRC S3-C06-R1 [cancel_pending_order,modify_pending_order_items; must_not]: The agent must not modify any attribute of a pending order other than the shipping address, the payment method, or the product item options.

## RET-MOD-01b
- gold quote: "and you should check its status before taking the action."
- gold reading: Check the status before modifying.
- GOLD RET-R015: The agent must look up the order's current status (get_order_details) before cancelling, modifying, returning, or exchanging it.
- aligned auto clauses: S3-C02
  - SRC S3-C01-R2 [cancel_pending_order,exchange_delivered_order_items,get_order_details,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must]: The agent must check the order's status before taking any modification action.
  - SRC S3-C01-R3 [cancel_pending_order,modify_pending_order_items; must_not]: The agent must not modify any attribute of a pending order other than the shipping address, the payment method, or the product item options.
  - SRC S3-C02-R1 [cancel_pending_order,exchange_delivered_order_items,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must]: The agent must check the status of the order before taking any modification action on that order.
  - SRC S3-C02-R2 [cancel_pending_order,exchange_delivered_order_items,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must]: The agent must modify the order only if its status is 'pending'.
  - SRC S3-C03-R2 [modify_pending_order_address; must]: The agent must check the order's status before taking the action to modify its shipping address.
  - SRC S3-C04-R1 [modify_pending_order_payment; must]: The agent must check the status of the order before modifying its payment method.
  - SRC S3-C05-R1 [cancel_pending_order,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment; must]: The agent must verify the order's status before taking any modification action on a pending order.
  - SIM S2-C05-R1 [cancel_pending_order; must]: The agent must verify the current order status by retrieving the order details before attempting cancellation.
  - SIM S6-C06-R1 [return_delivered_order_items; must_not]: The agent must not initiate the return action (which changes the order status to 'return requested' and notifies the user) unless the order status is 'delivered'.
  - SIM S6-C01-R2 [return_delivered_order_items; must]: The agent must check the order status before attempting to return the order.

## RET-MOD-02
- gold quote: "For a pending order, you can take actions to modify its shipping address, payment method, or product item options, but nothing else."
- gold reading: Only address, payment method, item options can be modified.
- GOLD RET-R022: The agent must not modify anything of a pending order other than its shipping address, payment method, or item options.
- aligned auto clauses: S3-C03, S3-C04, S3-C05, S3-C06
  - SRC S3-C01-R3 [cancel_pending_order,modify_pending_order_items; must_not]: The agent must not modify any attribute of a pending order other than the shipping address, the payment method, or the product item options.
  - SRC S3-C03-R1 [modify_pending_order_address; must_not]: The agent must not modify the shipping address of an order unless its status is 'pending'.
  - SRC S3-C03-R2 [modify_pending_order_address; must]: The agent must check the order's status before taking the action to modify its shipping address.
  - SRC S3-C04-R1 [modify_pending_order_payment; must]: The agent must check the status of the order before modifying its payment method.
  - SRC S3-C04-R2 [modify_pending_order_payment; must_not]: The agent must not modify the payment method of an order unless its status is 'pending'.
  - SRC S3-C05-R1 [cancel_pending_order,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment; must]: The agent must verify the order's status before taking any modification action on a pending order.
  - SRC S3-C06-R1 [cancel_pending_order,modify_pending_order_items; must_not]: The agent must not modify any attribute of a pending order other than the shipping address, the payment method, or the product item options.

## RET-MPAY-01
- gold quote: "The user can only choose a single payment method different from the original payment method."
- gold reading: New payment method: single, and different from the original.
- GOLD RET-R023: When modifying the payment of a pending order, the agent must switch to a single payment method that is different from the original payment method.
- aligned auto clauses: S4-C01
  - SRC S4-C01-R1 [modify_pending_order_payment; must]: The agent must ensure the user selects exactly one payment method.
  - SRC S4-C01-R2 [modify_pending_order_payment; must]: The agent must ensure the selected payment method is different from the original payment method.
  - SIM S1-C12-R4 [modify_pending_order_payment; must_not]: The agent must not modify the payment method of a pending order more than once.
  - SIM S3-C04-R1 [modify_pending_order_payment; must]: The agent must check the status of the order before modifying its payment method.

## RET-MPAY-02
- gold quote: "If the user wants the modify the payment method to gift card, it must have enough balance to cover the total amount."
- gold reading: Gift-card balance ≥ order total.
- GOLD RET-R024: When modifying the payment of a pending order to a gift card, the agent must ensure the gift card balance covers the order's total amount.
- aligned auto clauses: S4-C02
  - SRC S4-C02-R1 [modify_pending_order_payment; must_not]: The agent must not modify the payment method to gift card unless the user has enough balance to cover the total amount.
  - SIM S5-C09-R1 [modify_pending_order_payment; must]: The agent must ensure that any gift card provided by the user has enough balance to cover the price difference.
  - SIM S5-C06-R9 [modify_pending_order_items,modify_pending_order_payment; must]: The agent must ensure that if the user provides a gift card, it has enough balance to cover the price difference.

## RET-MITEM-01a
- gold quote: "This action can only be called once"
- gold reading: modify_pending_order_items at most once per order.
- GOLD RET-R016: The agent must call modify_pending_order_items at most once per order.
- aligned auto clauses: S5-C01
  - SRC S5-C01-R1 [modify_pending_order_items; must_not]: The agent must not perform item modification on a single pending order more than once.
  - SRC S5-C06-R2 [modify_pending_order_items; must_not]: The agent must not call modify_pending_order_items more than once for a pending order.
  - SRC S5-C06-R3 [cancel_pending_order,exchange_delivered_order_items,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must]: The agent must ensure the order status changes to 'pending (items modifed)' after performing the modification.
  - SIM S1-C12-R3 [modify_pending_order_address; must_not]: The agent must not modify the shipping address of a pending order more than once.
  - SIM S1-C12-R4 [modify_pending_order_payment; must_not]: The agent must not modify the payment method of a pending order more than once.

## RET-MITEM-01c
- gold quote: "the agent will not be able to modify or cancel the order anymore"
- gold reading: After items are modified, no further modify/cancel of that order.
- GOLD RET-R013: The agent must not cancel or modify (address, payment method, or items) an order unless its status is exactly 'pending'.
- aligned auto clauses: S5-C03
  - SRC S5-C02-R3 [cancel_pending_order,exchange_delivered_order_items,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must_not]: The agent must not be able to modify or cancel the order anymore
  - SRC S5-C03-R1 [cancel_pending_order,exchange_delivered_order_items,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must_not]: The agent must not modify the order anymore.
  - SRC S5-C03-R2 [cancel_pending_order; must_not]: The agent must not cancel the order anymore.
  - SIM S3-C04-R2 [modify_pending_order_payment; must_not]: The agent must not modify the payment method of an order unless its status is 'pending'.
  - SIM S3-C01-R3 [cancel_pending_order,modify_pending_order_items; must_not]: The agent must not modify any attribute of a pending order other than the shipping address, the payment method, or the product item options.
  - SIM S3-C06-R1 [cancel_pending_order,modify_pending_order_items; must_not]: The agent must not modify any attribute of a pending order other than the shipping address, the payment method, or the product item options.

## RET-MITEM-01d
- gold quote: "So confirm all the details are right and be cautious before taking this action."
- gold reading: Agent confirms all details before modifying items.
- GOLD RET-R005: The agent must obtain an explicit 'yes' from the user, given after the action details were listed, before calling any tool that updates the database.
- aligned auto clauses: S5-C04
  - SRC S5-C02-R4 [cancel_pending_order,exchange_delivered_order_items,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,modify_user_address,return_delivered_order_items; must]: The agent must ensure the user confirms all the details are right and be cautious before taking this action
  - SRC S5-C04-R1 [cancel_pending_order,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment; must]: The agent must obtain explicit user confirmation from the user before modifying any items in a pending order.
  - SRC S5-C04-R2 [cancel_pending_order,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment; must]: The agent must exercise caution before modifying pending order items.
  - SRC S5-C06-R6 [cancel_pending_order,exchange_delivered_order_items,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,modify_user_address,return_delivered_order_items; must]: The agent must obtain explicit user confirmation (yes/no) before proceeding with the modification.
  - SIM S0-C06-R3 [cancel_pending_order,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment; must]: The agent must list the modification details and obtain explicit user confirmation (yes) to proceed before modifying items in a pending order.
  - SIM S0-C06-R5 [exchange_delivered_order_items,return_delivered_order_items; must]: The agent must list the return details and obtain explicit user confirmation (yes) to proceed before returning items from a delivered order.

## RET-MITEM-01e
- gold quote: "In particular, remember to remind the customer to confirm they have provided all items to be modified."
- gold reading: Agent reminds the user to confirm the item list is complete.
- GOLD RET-R019: Before modifying items of a pending order or exchanging items of a delivered order, the agent must remind the user to confirm that they have provided all items to be modified or exchanged.
- aligned auto clauses: S5-C05
  - SRC S5-C02-R5 [exchange_delivered_order_items,modify_pending_order_items; must]: The agent must remind the customer to confirm they have provided all items to be modified
  - SRC S5-C06-R6 [cancel_pending_order,exchange_delivered_order_items,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,modify_user_address,return_delivered_order_items; must]: The agent must obtain explicit user confirmation (yes/no) before proceeding with the modification.
  - SIM S7-C03-R1 [exchange_delivered_order_items; must]: The agent must verify that the order status is 'delivered' before exchanging any items.
  - SIM S0-C06-R6 [exchange_delivered_order_items; must]: The agent must list the exchange details and obtain explicit user confirmation (yes) to proceed before exchanging delivered order items.

## RET-MITEM-02a
- gold quote: "For a pending order, each item can be modified to an available new item of the same product but of different product option."
- gold reading: Replacement item: same product, available, different option.
- GOLD RET-R025: When modifying or exchanging items, the agent must replace each item only with an item of the same product (no change of product type).
- GOLD RET-R026: When modifying or exchanging items, the agent must replace each item only with a new item that is available.
- GOLD RET-R027: When modifying or exchanging items, the agent must replace each item only with a new item of a different product option than the item it replaces.
- aligned auto clauses: S5-C06
  - SRC S5-C01-R1 [modify_pending_order_items; must_not]: The agent must not perform item modification on a single pending order more than once.
  - SRC S5-C02-R5 [exchange_delivered_order_items,modify_pending_order_items; must]: The agent must remind the customer to confirm they have provided all items to be modified
  - SRC S5-C02-R6 [exchange_delivered_order_items,modify_pending_order_items; must]: The agent must modify each item to an available new item of the same product but of different product option
  - SRC S5-C06-R1 [modify_pending_order_items; must]: The agent must modify each item in a pending order to an available new item of the same product but of a different product option, if an available new item exists.
  - SRC S5-C06-R2 [modify_pending_order_items; must_not]: The agent must not call modify_pending_order_items more than once for a pending order.
  - SRC S5-C06-R3 [cancel_pending_order,exchange_delivered_order_items,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must]: The agent must ensure the order status changes to 'pending (items modifed)' after performing the modification.
  - SRC S5-C06-R4 [modify_pending_order_items; must_not]: The agent must not modify an item to a different product type.
  - SRC S5-C06-R6 [cancel_pending_order,exchange_delivered_order_items,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,modify_user_address,return_delivered_order_items; must]: The agent must obtain explicit user confirmation (yes/no) before proceeding with the modification.
  - SRC S5-C06-R7 [exchange_delivered_order_items,modify_pending_order_items; must_not]: The agent must not modify an item if there is no available new item of the same product with a different option.
  - SRC S5-C06-R8 [cancel_pending_order,modify_pending_order_payment; must]: The agent must ensure the user provides a payment method to pay or receive refund of the price difference.
  - SRC S5-C06-R9 [modify_pending_order_items,modify_pending_order_payment; must]: The agent must ensure that if the user provides a gift card, it has enough balance to cover the price difference.

## RET-MITEM-02b
- gold quote: "There cannot be any change of product types, e.g. modify shirt to shoe."
- gold reading: No product-type change.
- GOLD RET-R025: When modifying or exchanging items, the agent must replace each item only with an item of the same product (no change of product type).
- aligned auto clauses: S5-C07
  - SRC S5-C02-R7 [modify_pending_order_items; must_not]: The agent must not change the product type during the modification
  - SRC S5-C06-R1 [modify_pending_order_items; must]: The agent must modify each item in a pending order to an available new item of the same product but of a different product option, if an available new item exists.
  - SRC S5-C06-R4 [modify_pending_order_items; must_not]: The agent must not modify an item to a different product type.
  - SRC S5-C07-R1 [modify_pending_order_items; must_not]: The agent must not change the product type of any item.
  - SIM S5-C02-R6 [exchange_delivered_order_items,modify_pending_order_items; must]: The agent must modify each item to an available new item of the same product but of different product option
  - SIM S5-C06-R7 [exchange_delivered_order_items,modify_pending_order_items; must_not]: The agent must not modify an item if there is no available new item of the same product with a different option.
  - SIM S7-C04-R1 [exchange_delivered_order_items; must_not]: The agent must not change the product type of any item when processing an exchange.

## RET-MITEM-03a
- gold quote: "The user must provide a payment method to pay or receive refund of the price difference."
- gold reading: A user-provided payment method is used for the price difference.
- GOLD RET-R028: When modifying or exchanging items, the agent must use a payment method provided by the user to pay or receive the price difference.
- aligned auto clauses: S5-C08
  - SRC S5-C02-R8 [cancel_pending_order,modify_pending_order_payment; must]: The agent must ensure the user provides a payment method to pay or receive refund of the price difference
  - SRC S5-C06-R8 [cancel_pending_order,modify_pending_order_payment; must]: The agent must ensure the user provides a payment method to pay or receive refund of the price difference.
  - SRC S5-C08-R1 [cancel_pending_order,modify_pending_order_payment; must]: The agent must obtain from the user a payment method to pay or receive refund of the price difference.
  - SIM S7-C05-R1 [cancel_pending_order,modify_pending_order_payment; must]: The agent must obtain a payment method from the user to pay or receive refund of the price difference.

## RET-MITEM-03b
- gold quote: "If the user provides a gift card, it must have enough balance to cover the price difference."
- gold reading: Gift-card balance ≥ price difference.
- GOLD RET-R029: When modifying or exchanging items with a gift card as the payment method, the agent must ensure the gift card balance covers the price difference.
- aligned auto clauses: S5-C09
  - SRC S5-C02-R9 [modify_pending_order_items,modify_pending_order_payment; must]: The agent must ensure that if the user provides a gift card, it has enough balance to cover the price difference
  - SRC S5-C06-R9 [modify_pending_order_items,modify_pending_order_payment; must]: The agent must ensure that if the user provides a gift card, it has enough balance to cover the price difference.
  - SRC S5-C09-R1 [modify_pending_order_payment; must]: The agent must ensure that any gift card provided by the user has enough balance to cover the price difference.
  - SIM S7-C06-R1 [modify_pending_order_payment; must]: The agent must verify that, if the user provides a gift card to cover the price difference, the balance on the gift card is at least the price difference.
  - SIM S4-C02-R1 [modify_pending_order_payment; must_not]: The agent must not modify the payment method to gift card unless the user has enough balance to cover the total amount.

## RET-RTN-01a
- gold quote: "An order can only be returned if its status is 'delivered'"
- gold reading: Return only if status == 'delivered'.
- GOLD RET-R014: The agent must not return or exchange items of an order unless its status is exactly 'delivered'.
- aligned auto clauses: S6-C01, S6-C02
  - SRC S6-C01-R2 [return_delivered_order_items; must]: The agent must check the order status before attempting to return the order.
  - SRC S6-C02-R1 [return_delivered_order_items; must_not]: The agent must not perform a return on an order unless the order status is 'delivered'.
  - SRC S6-C02-R2 [exchange_delivered_order_items,return_delivered_order_items; must]: The agent must check the order status by retrieving the order details before taking a return action.
  - SRC S6-C05-R1 [return_delivered_order_items; must]: The agent must change the order status to 'return requested' after user confirmation, only if the order status is 'delivered' and after you have checked its status before taking the action.
  - SRC S6-C06-R1 [return_delivered_order_items; must_not]: The agent must not initiate the return action (which changes the order status to 'return requested' and notifies the user) unless the order status is 'delivered'.
  - SIM S7-C02-R1 [exchange_delivered_order_items; must]: The agent must exchange an order only if its status is 'delivered'.
  - SIM S7-C03-R1 [exchange_delivered_order_items; must]: The agent must verify that the order status is 'delivered' before exchanging any items.

## RET-RTN-01b
- gold quote: "and you should check its status before taking the action."
- gold reading: Check the status before returning.
- GOLD RET-R015: The agent must look up the order's current status (get_order_details) before cancelling, modifying, returning, or exchanging it.
- aligned auto clauses: S6-C01, S6-C02
  - SRC S6-C01-R2 [return_delivered_order_items; must]: The agent must check the order status before attempting to return the order.
  - SRC S6-C02-R1 [return_delivered_order_items; must_not]: The agent must not perform a return on an order unless the order status is 'delivered'.
  - SRC S6-C02-R2 [exchange_delivered_order_items,return_delivered_order_items; must]: The agent must check the order status by retrieving the order details before taking a return action.
  - SRC S6-C05-R1 [return_delivered_order_items; must]: The agent must change the order status to 'return requested' after user confirmation, only if the order status is 'delivered' and after you have checked its status before taking the action.
  - SRC S6-C06-R1 [return_delivered_order_items; must_not]: The agent must not initiate the return action (which changes the order status to 'return requested' and notifies the user) unless the order status is 'delivered'.
  - SIM S2-C05-R1 [cancel_pending_order; must]: The agent must verify the current order status by retrieving the order details before attempting cancellation.

## RET-RTN-02
- gold quote: "The user needs to confirm the order id, the list of items to be returned, and a payment method to receive the refund."
- gold reading: User confirms order id, item list, refund method.
- GOLD RET-R030: Before returning items, the agent must have the user confirm the order id, the list of items to be returned, and the payment method to receive the refund.
- aligned auto clauses: S6-C03
  - SRC S6-C03-R1 [cancel_pending_order,exchange_delivered_order_items,get_order_details,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must]: The agent must obtain the user's confirmation of the order id.
  - SRC S6-C03-R2 [exchange_delivered_order_items,modify_pending_order_items,return_delivered_order_items; must]: The agent must obtain the user's confirmation of the list of items to be returned.
  - SRC S6-C03-R3 [cancel_pending_order; must]: The agent must obtain the user's confirmation of a payment method to receive the refund.
  - SRC S6-C04-R1 [cancel_pending_order; must]: The agent must ensure the refund is sent to either the original payment method or an existing gift card.
  - SRC S6-C04-R2 [cancel_pending_order; must]: The agent must obtain explicit user confirmation of the payment method to receive the refund.
  - SRC S6-C06-R2 [return_delivered_order_items; must]: The agent must explain the return details and ask for explicit user confirmation (yes/no) to proceed before initiating the return.
  - SIM S0-C06-R5 [exchange_delivered_order_items,return_delivered_order_items; must]: The agent must list the return details and obtain explicit user confirmation (yes) to proceed before returning items from a delivered order.
  - SIM S6-C06-R3 [return_delivered_order_items; must]: The agent must perform the action to change the order status to 'return requested' and ensure the user will receive an email regarding how to return items after the user has confirmed.

## RET-RTN-03
- gold quote: "The refund must either go to the original payment method, or an existing gift card."
- gold reading: Refund method ∈ {original payment method} ∪ {existing gift cards}.
- GOLD RET-R031: When returning items, the agent must send the refund either to the order's original payment method or to an existing gift card of the user.
- aligned auto clauses: S6-C04
  - SRC S6-C04-R1 [cancel_pending_order; must]: The agent must ensure the refund is sent to either the original payment method or an existing gift card.
  - SRC S6-C04-R2 [cancel_pending_order; must]: The agent must obtain explicit user confirmation of the payment method to receive the refund.
  - SIM S2-C06-R1 [cancel_pending_order; only_if]: The agent must refund the total via the original payment method immediately if the payment method is a gift card.
  - SIM S2-C06-R2 [cancel_pending_order; only_if]: The agent must refund the total via the original payment method in 5 to 7 business days if the payment method is not a gift card.

## RET-EXC-01a
- gold quote: "An order can only be exchanged if its status is 'delivered'"
- gold reading: Exchange only if status == 'delivered'.
- GOLD RET-R014: The agent must not return or exchange items of an order unless its status is exactly 'delivered'.
- aligned auto clauses: S7-C01, S7-C02
  - SRC S7-C02-R1 [exchange_delivered_order_items; must]: The agent must exchange an order only if its status is 'delivered'.
  - SRC S7-C02-R2 [exchange_delivered_order_items; must]: The agent must check the order status before taking the exchange action.
  - SRC S7-C03-R1 [exchange_delivered_order_items; must]: The agent must verify that the order status is 'delivered' before exchanging any items.
  - SRC S7-C03-R4 [exchange_delivered_order_items,modify_pending_order_items; must]: The agent must obtain explicit user confirmation from the user before performing the exchange.
  - SRC S7-C05-R1 [cancel_pending_order,modify_pending_order_payment; must]: The agent must obtain a payment method from the user to pay or receive refund of the price difference.
  - SRC S7-C07-R1 [exchange_delivered_order_items; must]: The agent must change the order status to 'exchange requested' after user confirmation, and only if the order status is 'delivered' and the status has been checked before taking the action.
  - SRC S7-C07-R2 [exchange_delivered_order_items; must_not]: The agent must not change the order status to 'exchange requested' before user confirmation.
  - SRC S7-C09-R1 [exchange_delivered_order_items; must_not]: The agent must not require the user to place a new order to exchange items from a delivered order.
  - SIM S6-C02-R1 [return_delivered_order_items; must_not]: The agent must not perform a return on an order unless the order status is 'delivered'.

## RET-EXC-01b
- gold quote: "and you should check its status before taking the action."
- gold reading: Check the status before exchanging.
- GOLD RET-R015: The agent must look up the order's current status (get_order_details) before cancelling, modifying, returning, or exchanging it.
- aligned auto clauses: S7-C01, S7-C02
  - SRC S7-C02-R1 [exchange_delivered_order_items; must]: The agent must exchange an order only if its status is 'delivered'.
  - SRC S7-C02-R2 [exchange_delivered_order_items; must]: The agent must check the order status before taking the exchange action.
  - SRC S7-C03-R1 [exchange_delivered_order_items; must]: The agent must verify that the order status is 'delivered' before exchanging any items.
  - SRC S7-C03-R4 [exchange_delivered_order_items,modify_pending_order_items; must]: The agent must obtain explicit user confirmation from the user before performing the exchange.
  - SRC S7-C05-R1 [cancel_pending_order,modify_pending_order_payment; must]: The agent must obtain a payment method from the user to pay or receive refund of the price difference.
  - SRC S7-C07-R1 [exchange_delivered_order_items; must]: The agent must change the order status to 'exchange requested' after user confirmation, and only if the order status is 'delivered' and the status has been checked before taking the action.
  - SRC S7-C07-R2 [exchange_delivered_order_items; must_not]: The agent must not change the order status to 'exchange requested' before user confirmation.
  - SRC S7-C09-R1 [exchange_delivered_order_items; must_not]: The agent must not require the user to place a new order to exchange items from a delivered order.
  - SIM S2-C05-R1 [cancel_pending_order; must]: The agent must verify the current order status by retrieving the order details before attempting cancellation.
  - SIM S6-C06-R1 [return_delivered_order_items; must_not]: The agent must not initiate the return action (which changes the order status to 'return requested' and notifies the user) unless the order status is 'delivered'.
  - SIM S6-C01-R2 [return_delivered_order_items; must]: The agent must check the order status before attempting to return the order.

## RET-EXC-01c
- gold quote: "In particular, remember to remind the customer to confirm they have provided all items to be exchanged."
- gold reading: Agent reminds the user to confirm the item list is complete.
- GOLD RET-R019: Before modifying items of a pending order or exchanging items of a delivered order, the agent must remind the user to confirm that they have provided all items to be modified or exchanged.
- aligned auto clauses: —
  - SIM S5-C02-R5 [exchange_delivered_order_items,modify_pending_order_items; must]: The agent must remind the customer to confirm they have provided all items to be modified
  - SIM S7-C03-R1 [exchange_delivered_order_items; must]: The agent must verify that the order status is 'delivered' before exchanging any items.
  - SIM S0-C06-R6 [exchange_delivered_order_items; must]: The agent must list the exchange details and obtain explicit user confirmation (yes) to proceed before exchanging delivered order items.

## RET-EXC-02a
- gold quote: "For a delivered order, each item can be exchanged to an available new item of the same product but of different product option."
- gold reading: Replacement item: same product, available, different option.
- GOLD RET-R025: When modifying or exchanging items, the agent must replace each item only with an item of the same product (no change of product type).
- GOLD RET-R026: When modifying or exchanging items, the agent must replace each item only with a new item that is available.
- GOLD RET-R027: When modifying or exchanging items, the agent must replace each item only with a new item of a different product option than the item it replaces.
- aligned auto clauses: S7-C03
  - SRC S7-C03-R1 [exchange_delivered_order_items; must]: The agent must verify that the order status is 'delivered' before exchanging any items.
  - SRC S7-C03-R2 [exchange_delivered_order_items; must]: The agent must exchange each item in the delivered order to an available new item of the same product but with a different product option.
  - SRC S7-C03-R3 [exchange_delivered_order_items,modify_pending_order_items; must_not]: The agent must not exchange any item unless there exists an available new item of the same product with a different option.
  - SRC S7-C03-R4 [exchange_delivered_order_items,modify_pending_order_items; must]: The agent must obtain explicit user confirmation from the user before performing the exchange.
  - SRC S7-C04-R1 [exchange_delivered_order_items; must_not]: The agent must not change the product type of any item when processing an exchange.
  - SRC S7-C05-R1 [cancel_pending_order,modify_pending_order_payment; must]: The agent must obtain a payment method from the user to pay or receive refund of the price difference.
  - SRC S7-C09-R1 [exchange_delivered_order_items; must_not]: The agent must not require the user to place a new order to exchange items from a delivered order.
  - SIM S5-C02-R6 [exchange_delivered_order_items,modify_pending_order_items; must]: The agent must modify each item to an available new item of the same product but of different product option
  - SIM S5-C06-R7 [exchange_delivered_order_items,modify_pending_order_items; must_not]: The agent must not modify an item if there is no available new item of the same product with a different option.
  - SIM S5-C06-R1 [modify_pending_order_items; must]: The agent must modify each item in a pending order to an available new item of the same product but of a different product option, if an available new item exists.

## RET-EXC-02b
- gold quote: "There cannot be any change of product types, e.g. modify shirt to shoe."
- gold reading: No product-type change.
- GOLD RET-R025: When modifying or exchanging items, the agent must replace each item only with an item of the same product (no change of product type).
- aligned auto clauses: S7-C04
  - SRC S7-C03-R2 [exchange_delivered_order_items; must]: The agent must exchange each item in the delivered order to an available new item of the same product but with a different product option.
  - SRC S7-C03-R3 [exchange_delivered_order_items,modify_pending_order_items; must_not]: The agent must not exchange any item unless there exists an available new item of the same product with a different option.
  - SRC S7-C04-R1 [exchange_delivered_order_items; must_not]: The agent must not change the product type of any item when processing an exchange.
  - SRC S7-C05-R1 [cancel_pending_order,modify_pending_order_payment; must]: The agent must obtain a payment method from the user to pay or receive refund of the price difference.
  - SRC S7-C09-R1 [exchange_delivered_order_items; must_not]: The agent must not require the user to place a new order to exchange items from a delivered order.
  - SIM S5-C02-R6 [exchange_delivered_order_items,modify_pending_order_items; must]: The agent must modify each item to an available new item of the same product but of different product option
  - SIM S5-C06-R7 [exchange_delivered_order_items,modify_pending_order_items; must_not]: The agent must not modify an item if there is no available new item of the same product with a different option.

## RET-EXC-03a
- gold quote: "The user must provide a payment method to pay or receive refund of the price difference."
- gold reading: A user-provided payment method is used for the price difference.
- GOLD RET-R028: When modifying or exchanging items, the agent must use a payment method provided by the user to pay or receive the price difference.
- aligned auto clauses: S7-C05
  - SRC S7-C05-R1 [cancel_pending_order,modify_pending_order_payment; must]: The agent must obtain a payment method from the user to pay or receive refund of the price difference.
  - SRC S7-C06-R1 [modify_pending_order_payment; must]: The agent must verify that, if the user provides a gift card to cover the price difference, the balance on the gift card is at least the price difference.
  - SRC S7-C09-R1 [exchange_delivered_order_items; must_not]: The agent must not require the user to place a new order to exchange items from a delivered order.
  - SIM S5-C08-R1 [cancel_pending_order,modify_pending_order_payment; must]: The agent must obtain from the user a payment method to pay or receive refund of the price difference.
  - SIM S5-C06-R8 [cancel_pending_order,modify_pending_order_payment; must]: The agent must ensure the user provides a payment method to pay or receive refund of the price difference.

## RET-EXC-03b
- gold quote: "If the user provides a gift card, it must have enough balance to cover the price difference."
- gold reading: Gift-card balance ≥ price difference.
- GOLD RET-R029: When modifying or exchanging items with a gift card as the payment method, the agent must ensure the gift card balance covers the price difference.
- aligned auto clauses: S7-C06
  - SRC S7-C05-R1 [cancel_pending_order,modify_pending_order_payment; must]: The agent must obtain a payment method from the user to pay or receive refund of the price difference.
  - SRC S7-C06-R1 [modify_pending_order_payment; must]: The agent must verify that, if the user provides a gift card to cover the price difference, the balance on the gift card is at least the price difference.
  - SRC S7-C09-R1 [exchange_delivered_order_items; must_not]: The agent must not require the user to place a new order to exchange items from a delivered order.
  - SIM S4-C02-R1 [modify_pending_order_payment; must_not]: The agent must not modify the payment method to gift card unless the user has enough balance to cover the total amount.
  - SIM S5-C06-R9 [modify_pending_order_items,modify_pending_order_payment; must]: The agent must ensure that if the user provides a gift card, it has enough balance to cover the price difference.

# All auto rules

- S0-C01-R1 [cancel_pending_order,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment; may; src S0-C01]: The agent must help users cancel or modify pending orders.
- S0-C01-R2 [exchange_delivered_order_items,return_delivered_order_items; may; src S0-C01]: The agent must help users return or exchange delivered orders.
- S0-C01-R3 [modify_user_address; may; src S0-C01]: The agent must help users modify their default user address.
- S0-C01-R4 [find_user_id_by_email,find_user_id_by_name_zip,get_order_details,get_product_details,get_user_details,list_all_product_types; may; src S0-C01]: The agent must provide information about their own profile, orders, and related products.
- S0-C02-R1 [cancel_pending_order,exchange_delivered_order_items,find_user_id_by_email,find_user_id_by_name_zip,get_order_details,get_user_details,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must; src S0-C02,S0-C03]: The agent must authenticate the user identity at the beginning of the conversation by locating the user id via email, or via name + zip code.
- S0-C04-R1 [cancel_pending_order,exchange_delivered_order_items,get_order_details,get_user_details,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,respond_to_user,return_delivered_order_items; must_not; src S0-C04,S0-C02,S0-C03]: The agent must not provide information about orders unless the user has been authenticated.
- S0-C04-R2 [get_product_details,list_all_product_types,respond_to_user; must_not; src S0-C04,S0-C02,S0-C03]: The agent must not provide information about products unless the user has been authenticated.
- S0-C04-R3 [find_user_id_by_email,find_user_id_by_name_zip,get_order_details,get_user_details; must_not; src S0-C04,S0-C02,S0-C03]: The agent must not provide profile information unless the user has been authenticated.
- S0-C05-R1 [cancel_pending_order,exchange_delivered_order_items,find_user_id_by_email,find_user_id_by_name_zip,get_order_details,get_user_details,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must_not; src S0-C05]: The agent must not provide assistance to any user other than the one currently participating in the conversation.
- S0-C05-R2 [cancel_pending_order,exchange_delivered_order_items,find_user_id_by_email,find_user_id_by_name_zip,get_order_details,get_user_details,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,modify_user_address,return_delivered_order_items; must; src S0-C05]: The agent must deny requests for tasks related to any other user.
- S0-C06-R1 [cancel_pending_order; must; src S0-C06]: The agent must list the cancellation details and obtain explicit user confirmation (yes) to proceed before cancelling a pending order.
- S0-C06-R2 [modify_pending_order_address; must; src S0-C06]: The agent must list the modification details and obtain explicit user confirmation (yes) to proceed before modifying the shipping address of a pending order.
- S0-C06-R3 [cancel_pending_order,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment; must; src S0-C06]: The agent must list the modification details and obtain explicit user confirmation (yes) to proceed before modifying items in a pending order.
- S0-C06-R4 [modify_pending_order_payment; must; src S0-C06]: The agent must list the modification details and obtain explicit user confirmation (yes) to proceed before modifying the payment method of a pending order.
- S0-C06-R5 [exchange_delivered_order_items,return_delivered_order_items; must; src S0-C06]: The agent must list the return details and obtain explicit user confirmation (yes) to proceed before returning items from a delivered order.
- S0-C06-R6 [exchange_delivered_order_items; must; src S0-C06]: The agent must list the exchange details and obtain explicit user confirmation (yes) to proceed before exchanging delivered order items.
- S0-C07-R1 [respond_to_user; must_not; src S0-C07]: The agent must not make up any information not provided by the user or the tools.
- S0-C07-R2 [respond_to_user,transfer_to_human_agents; must_not; src S0-C07]: The agent must not make up any knowledge not provided by the user or the tools.
- S0-C07-R3 [respond_to_user; must_not; src S0-C07]: The agent must not make up any procedures not provided by the user or the tools.
- S0-C07-R4 [respond_to_user; must_not; src S0-C07]: The agent must not give subjective recommendations or comments.
- S0-C08-R1 [calculate,cancel_pending_order,exchange_delivered_order_items,find_user_id_by_email,find_user_id_by_name_zip,get_order_details,get_product_details,get_user_details,list_all_product_types,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,modify_user_address,return_delivered_order_items,transfer_to_human_agents; must_not; src S0-C08]: The agent must not initiate a second tool call while a first tool call is in progress.
- S0-C08-R2 [cancel_pending_order,exchange_delivered_order_items,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,respond_to_user,return_delivered_order_items,transfer_to_human_agents; must_not; src S0-C08]: The agent must not respond to the user while a tool call is in progress.
- S0-C09-R1 [calculate,cancel_pending_order,exchange_delivered_order_items,find_user_id_by_email,find_user_id_by_name_zip,get_order_details,get_product_details,get_user_details,list_all_product_types,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,modify_user_address,return_delivered_order_items,think,transfer_to_human_agents; must_not; src S0-C09]: The agent must not call any tool while responding to the user.
- S0-C10-R1 [transfer_to_human_agents; if_and_only_if; src S0-C10,S0-C01]: The agent must transfer to a human agent if the request cannot be handled within the scope of your actions.
- S0-C10-R2 [transfer_to_human_agents; if_and_only_if; src S0-C10,S0-C01]: The agent must not transfer to a human agent if the request can be handled within the scope of your actions.
- S1-C12-R1 [exchange_delivered_order_items; must_not; src S1-C12]: The agent must not call the operation to exchange items in a delivered order more than once.
- S1-C12-R3 [modify_pending_order_address; must_not; src S1-C12]: The agent must not modify the shipping address of a pending order more than once.
- S1-C12-R4 [modify_pending_order_payment; must_not; src S1-C12]: The agent must not modify the payment method of a pending order more than once.
- S1-C13-R1 [cancel_pending_order,exchange_delivered_order_items,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must; src S1-C13,S1-C12]: The agent must ensure that all items to be changed are collected into a list before making a tool call that changes an order.
- S1-C13-R2 [exchange_delivered_order_items,modify_pending_order_items,return_delivered_order_items; must_not; src S1-C13,S1-C12]: The agent must not perform an order-item change tool call more than once.
- S2-C01-R1 [cancel_pending_order; must_not; src S2-C01,S2-C02]: The agent must not cancel an order unless the order status is 'pending'.
- S2-C02-R1 [cancel_pending_order; must; src S2-C02]: The agent must check the order status before taking the cancellation action.
- S2-C03-R1 [cancel_pending_order; must; src S2-C03,S2-C01]: The agent must obtain explicit user confirmation of the order id before cancelling the order, and the cancellation may be performed only if the order status is 'pending'.
- S2-C04-R1 [cancel_pending_order; must; src S2-C04]: The agent must confirm the cancellation reason as either 'no longer needed' or 'ordered by mistake'.
- S2-C05-R1 [cancel_pending_order; must; src S2-C05,S2-C02]: The agent must verify the current order status by retrieving the order details before attempting cancellation.
- S2-C05-R2 [cancel_pending_order; must_not; src S2-C05,S2-C01]: The agent must not cancel the order unless its status is 'pending'.
- S2-C05-R3 [cancel_pending_order,exchange_delivered_order_items,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,modify_user_address,return_delivered_order_items; must; src S2-C05]: The agent must obtain explicit user confirmation to proceed.
- S2-C05-R4 [cancel_pending_order; must; src S2-C05,S2-C03]: The agent must require the user to confirm the order id before cancelling.
- S2-C05-R5 [cancel_pending_order; must; src S2-C05,S2-C04]: The agent must require explicit confirmation of the cancellation reason from the user, either 'no longer needed' or 'ordered by mistake'.
- S2-C05-R6 [cancel_pending_order; must; src S2-C05,S2-C06]: The agent must call the cancellation tool to change the order status to 'cancelled' and process the refund when the user has confirmed.
- S2-C06-R1 [cancel_pending_order; only_if; src S2-C06,S4-C04]: The agent must refund the total via the original payment method immediately if the payment method is a gift card.
- S2-C06-R2 [cancel_pending_order; only_if; src S2-C06,S4-C04]: The agent must refund the total via the original payment method in 5 to 7 business days if the payment method is not a gift card.
- S3-C01-R2 [cancel_pending_order,exchange_delivered_order_items,get_order_details,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must; src S3-C01,S3-C02]: The agent must check the order's status before taking any modification action.
- S3-C01-R3 [cancel_pending_order,modify_pending_order_items; must_not; src S3-C01,S3-C02,S3-C03,S3-C04,S3-C05,S3-C06]: The agent must not modify any attribute of a pending order other than the shipping address, the payment method, or the product item options.
- S3-C02-R1 [cancel_pending_order,exchange_delivered_order_items,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must; src S3-C02,S3-C01]: The agent must check the status of the order before taking any modification action on that order.
- S3-C02-R2 [cancel_pending_order,exchange_delivered_order_items,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must; src S3-C02,S3-C01]: The agent must modify the order only if its status is 'pending'.
- S3-C03-R1 [modify_pending_order_address; must_not; src S3-C03,S3-C01]: The agent must not modify the shipping address of an order unless its status is 'pending'.
- S3-C03-R2 [modify_pending_order_address; must; src S3-C03,S3-C02]: The agent must check the order's status before taking the action to modify its shipping address.
- S3-C04-R1 [modify_pending_order_payment; must; src S3-C04,S3-C02]: The agent must check the status of the order before modifying its payment method.
- S3-C04-R2 [modify_pending_order_payment; must_not; src S3-C04,S3-C01]: The agent must not modify the payment method of an order unless its status is 'pending'.
- S3-C05-R1 [cancel_pending_order,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment; must; src S3-C05,S3-C02,S3-C01]: The agent must verify the order's status before taking any modification action on a pending order.
- S3-C06-R1 [cancel_pending_order,modify_pending_order_items; must_not; src S3-C06,S3-C01,S3-C03,S3-C04,S3-C05]: The agent must not modify any attribute of a pending order other than the shipping address, the payment method, or the product item options.
- S4-C01-R1 [modify_pending_order_payment; must; src S4-C01]: The agent must ensure the user selects exactly one payment method.
- S4-C01-R2 [modify_pending_order_payment; must; src S4-C01]: The agent must ensure the selected payment method is different from the original payment method.
- S4-C02-R1 [modify_pending_order_payment; must_not; src S4-C02]: The agent must not modify the payment method to gift card unless the user has enough balance to cover the total amount.
- S4-C03-R1 [cancel_pending_order,exchange_delivered_order_items,return_delivered_order_items; must; src S4-C03]: The agent must ensure that after user confirmation, the order status will be kept 'pending'.
- S5-C01-R1 [modify_pending_order_items; must_not; src S5-C01,S5-C06]: The agent must not perform item modification on a single pending order more than once.
- S5-C02-R3 [cancel_pending_order,exchange_delivered_order_items,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must_not; src S5-C02,S5-C03]: The agent must not be able to modify or cancel the order anymore
- S5-C02-R4 [cancel_pending_order,exchange_delivered_order_items,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,modify_user_address,return_delivered_order_items; must; src S5-C02,S5-C04]: The agent must ensure the user confirms all the details are right and be cautious before taking this action
- S5-C02-R5 [exchange_delivered_order_items,modify_pending_order_items; must; src S5-C02,S5-C05,S5-C06]: The agent must remind the customer to confirm they have provided all items to be modified
- S5-C02-R6 [exchange_delivered_order_items,modify_pending_order_items; must; src S5-C02,S5-C06]: The agent must modify each item to an available new item of the same product but of different product option
- S5-C02-R7 [modify_pending_order_items; must_not; src S5-C02,S5-C07]: The agent must not change the product type during the modification
- S5-C02-R8 [cancel_pending_order,modify_pending_order_payment; must; src S5-C02,S5-C08]: The agent must ensure the user provides a payment method to pay or receive refund of the price difference
- S5-C02-R9 [modify_pending_order_items,modify_pending_order_payment; must; src S5-C02,S5-C09]: The agent must ensure that if the user provides a gift card, it has enough balance to cover the price difference
- S5-C03-R1 [cancel_pending_order,exchange_delivered_order_items,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must_not; src S5-C03]: The agent must not modify the order anymore.
- S5-C03-R2 [cancel_pending_order; must_not; src S5-C03]: The agent must not cancel the order anymore.
- S5-C04-R1 [cancel_pending_order,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment; must; src S5-C04]: The agent must obtain explicit user confirmation from the user before modifying any items in a pending order.
- S5-C04-R2 [cancel_pending_order,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment; must; src S5-C04]: The agent must exercise caution before modifying pending order items.
- S5-C06-R1 [modify_pending_order_items; must; src S5-C06,S5-C07]: The agent must modify each item in a pending order to an available new item of the same product but of a different product option, if an available new item exists.
- S5-C06-R2 [modify_pending_order_items; must_not; src S5-C06,S1-C12,S5-C01,S5-C02]: The agent must not call modify_pending_order_items more than once for a pending order.
- S5-C06-R3 [cancel_pending_order,exchange_delivered_order_items,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must; src S5-C06,S5-C01,S5-C02]: The agent must ensure the order status changes to 'pending (items modifed)' after performing the modification.
- S5-C06-R4 [modify_pending_order_items; must_not; src S5-C06,S5-C07]: The agent must not modify an item to a different product type.
- S5-C06-R6 [cancel_pending_order,exchange_delivered_order_items,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,modify_user_address,return_delivered_order_items; must; src S5-C04,S5-C06,S5-C05]: The agent must obtain explicit user confirmation (yes/no) before proceeding with the modification.
- S5-C06-R7 [exchange_delivered_order_items,modify_pending_order_items; must_not; src S5-C06]: The agent must not modify an item if there is no available new item of the same product with a different option.
- S5-C06-R8 [cancel_pending_order,modify_pending_order_payment; must; src S5-C08,S5-C06]: The agent must ensure the user provides a payment method to pay or receive refund of the price difference.
- S5-C06-R9 [modify_pending_order_items,modify_pending_order_payment; must; src S5-C09,S5-C06]: The agent must ensure that if the user provides a gift card, it has enough balance to cover the price difference.
- S5-C07-R1 [modify_pending_order_items; must_not; src S5-C07]: The agent must not change the product type of any item.
- S5-C08-R1 [cancel_pending_order,modify_pending_order_payment; must; src S5-C08]: The agent must obtain from the user a payment method to pay or receive refund of the price difference.
- S5-C09-R1 [modify_pending_order_payment; must; src S5-C09]: The agent must ensure that any gift card provided by the user has enough balance to cover the price difference.
- S6-C01-R2 [return_delivered_order_items; must; src S6-C01,S6-C02]: The agent must check the order status before attempting to return the order.
- S6-C02-R1 [return_delivered_order_items; must_not; src S6-C02,S6-C01]: The agent must not perform a return on an order unless the order status is 'delivered'.
- S6-C02-R2 [exchange_delivered_order_items,return_delivered_order_items; must; src S6-C02,S6-C01]: The agent must check the order status by retrieving the order details before taking a return action.
- S6-C03-R1 [cancel_pending_order,exchange_delivered_order_items,get_order_details,modify_pending_order_address,modify_pending_order_items,modify_pending_order_payment,return_delivered_order_items; must; src S6-C03]: The agent must obtain the user's confirmation of the order id.
- S6-C03-R2 [exchange_delivered_order_items,modify_pending_order_items,return_delivered_order_items; must; src S6-C03]: The agent must obtain the user's confirmation of the list of items to be returned.
- S6-C03-R3 [cancel_pending_order; must; src S6-C03]: The agent must obtain the user's confirmation of a payment method to receive the refund.
- S6-C04-R1 [cancel_pending_order; must; src S6-C04,S6-C03]: The agent must ensure the refund is sent to either the original payment method or an existing gift card.
- S6-C04-R2 [cancel_pending_order; must; src S6-C04,S6-C03]: The agent must obtain explicit user confirmation of the payment method to receive the refund.
- S6-C05-R1 [return_delivered_order_items; must; src S6-C05,S6-C01,S6-C02]: The agent must change the order status to 'return requested' after user confirmation, only if the order status is 'delivered' and after you have checked its status before taking the action.
- S6-C06-R1 [return_delivered_order_items; must_not; src S6-C06,S6-C01,S6-C02]: The agent must not initiate the return action (which changes the order status to 'return requested' and notifies the user) unless the order status is 'delivered'.
- S6-C06-R2 [return_delivered_order_items; must; src S6-C06,S6-C03,S6-C05]: The agent must explain the return details and ask for explicit user confirmation (yes/no) to proceed before initiating the return.
- S6-C06-R3 [return_delivered_order_items; must; src S6-C06,S6-C05]: The agent must perform the action to change the order status to 'return requested' and ensure the user will receive an email regarding how to return items after the user has confirmed.
- S7-C02-R1 [exchange_delivered_order_items; must; src S7-C02,S7-C01]: The agent must exchange an order only if its status is 'delivered'.
- S7-C02-R2 [exchange_delivered_order_items; must; src S7-C02,S7-C01]: The agent must check the order status before taking the exchange action.
- S7-C03-R1 [exchange_delivered_order_items; must; src S7-C03,S7-C02,S7-C01]: The agent must verify that the order status is 'delivered' before exchanging any items.
- S7-C03-R2 [exchange_delivered_order_items; must; src S7-C03,S7-C04]: The agent must exchange each item in the delivered order to an available new item of the same product but with a different product option.
- S7-C03-R3 [exchange_delivered_order_items,modify_pending_order_items; must_not; src S7-C03,S7-C04]: The agent must not exchange any item unless there exists an available new item of the same product with a different option.
- S7-C03-R4 [exchange_delivered_order_items,modify_pending_order_items; must; src S7-C03,S7-C02]: The agent must obtain explicit user confirmation from the user before performing the exchange.
- S7-C04-R1 [exchange_delivered_order_items; must_not; src S7-C04,S7-C03]: The agent must not change the product type of any item when processing an exchange.
- S7-C05-R1 [cancel_pending_order,modify_pending_order_payment; must; src S7-C05,S7-C02,S7-C03,S7-C04,S7-C06,S7-C07,S7-C08]: The agent must obtain a payment method from the user to pay or receive refund of the price difference.
- S7-C06-R1 [modify_pending_order_payment; must; src S7-C06,S7-C05]: The agent must verify that, if the user provides a gift card to cover the price difference, the balance on the gift card is at least the price difference.
- S7-C07-R1 [exchange_delivered_order_items; must; src S7-C07,S7-C02,S7-C01]: The agent must change the order status to 'exchange requested' after user confirmation, and only if the order status is 'delivered' and the status has been checked before taking the action.
- S7-C07-R2 [exchange_delivered_order_items; must_not; src S7-C07,S7-C02,S7-C01]: The agent must not change the order status to 'exchange requested' before user confirmation.
- S7-C07-R3 [return_delivered_order_items; must; src S7-C07,S6-C05,S6-C06,S7-C08]: The agent must send an email to the user regarding how to return items after user confirmation.
- S7-C08-R1 [exchange_delivered_order_items; must_not; src S7-C08,S7-C07]: The agent must not change the order status to 'exchange requested' before explicit user confirmation.
- S7-C08-R2 [return_delivered_order_items; must_not; src S7-C08,S7-C07]: The agent must not send an email regarding how to return items before explicit user confirmation.
- S7-C08-R3 [exchange_delivered_order_items,modify_pending_order_items; must; src S7-C08,S7-C07]: The agent must change the order status to 'exchange requested' after explicit user confirmation.
- S7-C08-R4 [exchange_delivered_order_items,return_delivered_order_items; must; src S7-C08,S7-C07]: The agent must send an email regarding how to return items after explicit user confirmation.
- S7-C09-R1 [exchange_delivered_order_items; must_not; src S7-C09,S7-C02,S7-C03,S7-C04,S7-C05,S7-C06,S7-C07,S7-C08]: The agent must not require the user to place a new order to exchange items from a delivered order.
