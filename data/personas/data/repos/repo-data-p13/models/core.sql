SELECT customer_id, SUM(amount) OVER (PARTITION BY customer_id) FROM orders;
select * from {{ ref('stg_orders') }}
