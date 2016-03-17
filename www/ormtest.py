import orm
from Model import User, Blog, Comment
import asyncio
def test(loop):
    yield from orm.create_pool(loop, user='www-data', password='www-data', db='awesome')

    u = User(name='Test', email='test@example.com', passwd='1234567890', image='about:blank')

    yield from u.save()



loop = asyncio.get_event_loop()
loop.run_until_complete(test(loop))
__pool = orm.__pool
__pool.close()
loop.run_until_complete(__pool.wait_closed())
loop.close()