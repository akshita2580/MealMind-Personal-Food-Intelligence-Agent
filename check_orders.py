"""Check orders in database."""
from sqlmodel import select
from src.database import get_session, create_db_and_tables
from src.models import Order, User, SwiggyConnection

create_db_and_tables()

with get_session() as session:
    orders = session.exec(select(Order)).all()
    users = session.exec(select(User)).all()
    conns = session.exec(select(SwiggyConnection)).all()
    
    print(f"Total orders: {len(orders)}")
    print(f"Total users: {len(users)}")
    print(f"Total connections: {len(conns)}")
    print()
    
    if orders:
        print("First 15 orders:")
        for o in orders[:15]:
            print(f"  {o.restaurant_name} - {o.order_id}")
    
    print()
    if users:
        print("Users:")
        for u in users:
            print(f"  telegram_id={u.telegram_id} id={u.id}")
    
    print()
    if conns:
        print("Connections:")
        for c in conns:
            print(f"  user_id={c.user_id} status={c.status}")
