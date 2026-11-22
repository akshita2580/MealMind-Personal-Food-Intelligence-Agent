from sqlmodel import select, Session
from src.database import get_engine
from src.models import Order, OrderItem

engine = get_engine()
with Session(engine) as s:
    # Delete test orders
    test_ids = [f'same_time_{i}' for i in range(20)] + [f'order_{i}' for i in range(1, 30)]
    
    items = s.exec(select(OrderItem).where(OrderItem.order_id.in_(test_ids))).all()
    for i in items:
        s.delete(i)
    s.commit()
    
    orders = s.exec(select(Order).where(Order.order_id.in_(test_ids))).all()
    for o in orders:
        s.delete(o)
    s.commit()
    
    print(f'Cleaned {len(orders)} test orders and {len(items)} items')
    
    remaining = s.exec(select(Order)).all()
    print(f'Remaining orders: {len(remaining)}')
    for o in remaining[:5]:
        print(f'  {o.restaurant_name} - {o.order_id}')
