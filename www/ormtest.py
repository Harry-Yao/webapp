import orm
from Model import User, Blog, Comment
import asyncio

def test_save(loop):
    yield from orm.create_pool(loop, user='www-data', password='www-data', db='awesome')

    u = User(name='hi', email='hi@example.com',
             passwd='hi', image='about:blank')
    # pdb.set_trace()
    yield from u.save()

@asyncio.coroutine
def test(loop):
    yield from orm.create_pool(loop, user='www-data', password='www-data', db='awesome')

    #u = User(name='yao', email='67344@qq.com', passwd='1234567890', image='about:blank')
    rs = yield from User.findNumber('email')
    print(rs)
'''
@asyncio.coroutine
def test_findAll(loop):
    yield from orm.create_pool(loop, user='www-data', password='www-data', db='awesome')


    u = User(id='001458178908373260a72a1503d42cb83520d4a18dfef87000')

    yield from u.remove()
'''

loop = asyncio.get_event_loop()
loop.run_until_complete(test(loop))
__pool = orm.__pool
__pool.close()
loop.run_until_complete(__pool.wait_closed())
loop.close()