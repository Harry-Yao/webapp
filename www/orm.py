# -*- coding: utf-8 -*-

import asyncio,logging
import aiomysql

def log(sql, args=()):
    logging.info('SQL:%s' % sql)

@asyncio.coroutine
def create_pool(loop,**kw):
    logging.info('create database connection pool...')
    global __pool
    __pool = yield from  aiomysql.create_pool(
        host=kw.get('host','localhost'),
        port=kw.get('port',3306),
        user = kw['user'],							#user取传入的参数key为user的值
		password = kw['password'],
        db=kw['db'],
        charset=kw.get('charset','utf8'),
        autocommit=kw.get('autocommit',True),
        maxsize=kw.get('maxsize',10),
        minsize=kw.get('minsize',1),
        loop = loop
    )

@asyncio.coroutine
def select(sql, args, size=None):
    logging.info('select = %s and args = %s' % (sql, args))
    global __pool
    with (yield from __pool) as conn:
        cur = yield  from  conn.cursor(aiomysql.DictCursor)
        yield from cur.execute(sql.replace('?','%s'),args or ())
        if size:
            rs = yield from cur.fetchmany(size)
        else:
            rs = yield from cur.fetchall()
        yield from cur.close()
        logging.info('rows returned: %s' % len(rs))
        return rs

@asyncio.coroutine
def execute(sql, args, autocommit=True):
    log(sql)
    with (yield from __pool) as conn:
        if not autocommit:
            yield from conn.begin()
        try:
            cur = yield from conn.cursor()
            yield from cur.execute(sql.replace('?','%s'),args)
            affected = cur.rowcount
            yield from cur.close()
        except BaseException as e:
            if not autocommit:
                yield from conn.rollback()
            raise
        return affected

class ModelMetaclass(type):
    def __new__(cls, name, bases, attrs):
        if name == 'Model':
            return type.__new__(cls, name, bases, attrs)
        tableName = attrs.get('__table__',None) or name
        logging.info('found model:%s (table:%s)' % (name, tableName))
        mappings = dict()
        fields = []
        primaryKey = None
        for k, v in attrs.items():
            if isinstance(v, Field):
                logging.info('found mapping: %s ==> %s' % (k, v))
                mappings[k] = v
                if v.primary_key:
                     if primaryKey:
                         raise RuntimeError(
                            'Duplicate primary key for field: %s' % k)
                     primaryKey = k
                else:
                    fields.append(k)

        if not primaryKey:
             raise RuntimeError('Priamry key not found.')

        for k in mappings.keys():
            attrs.pop(k)

        escaped_fields = list(map(lambda f: r"`%s`" % f, fields))
        attrs['__mappings__'] = mappings
        attrs['__table__'] = tableName
        attrs['__primary_key__'] = primaryKey
        attrs['__fields__'] = fields
        attrs['__select__'] = "select `%s`,%s from `%s`" % (
            primaryKey, ','.join(escaped_fields), tableName)
        attrs['__update__'] = 'update `%s` set %s where `%s`=?' % (tableName, ', '.join(
            map(lambda f: '`%s`=?' % (mappings.get(f).name or f), fields)), primaryKey)
        attrs['__delete__'] = 'delete from `%s` where `%s`=?' % (
            tableName, primaryKey)
        attrs['__insert__'] = 'insert into `%s` (%s, `%s`) values (%s)' % (tableName, ', '.join(
            escaped_fields), primaryKey, create_args_string(len(escaped_fields) + 1))
        return type.__new__(cls, name, bases, attrs)

def create_args_string(num):
    L = []
    for n in range(num):
        L.append('?')
    return ', '.join(L)

class Model(dict, metaclass=ModelMetaclass):
    def __init__(self, **kw):
        super(Model, self).__init__(**kw)

    def __getattr__(self, key):
        try:
            return self[key]  # 如果存在则正常返回
        except KeyError:
            raise AttributeError(
                r"'Model' object has no attribute '%s'" % key)

    def __setattr__(self, key, value):
        self[key] = value

    def getValue(self, key):
        return getattr(self, key, None)

    def getValueOrDefault(self, key):
        value = getattr(self, key, None)
        if value is None:		# 不存在这样的值则直接返回
            # self.__mapping__在metaclass中，用于保存不同实例属性在Model基类中的映射关系
            field = self.__mappings__[key]
            if field.default is not None:  # 如果实例的域存在默认值，则使用默认值
                # field.default是callable的话则直接调用
                value = field.default() if callable(field.default) else field.default
                logging.debug('using default value for %s:%s' %
                              (key, str(value)))
                setattr(self, key, value)
        return value

    @classmethod    # 类方法
    @asyncio.coroutine
    def findAll(cls, where=None, args=None, **kw):
        sql = [cls.__select__]  # 获取默认的select语句
        if where:   # 如果有where语句，则修改sql变量
            # 这里不用协程，是因为不需要等待数据返回
            sql.append('where')  # sql里面加上where关键字
            sql.append(where)   # 这里的where实际上是colName='xxx'这样的条件表达式
        if args is None:    # 什么参数?
            args = []

        orderBy = kw.get('orderBy', None)    # 从kw中查看是否有orderBy属性
        if orderBy:
            sql.append('order by')
            sql.append(orderBy)

        limit = kw.get('limit', None)    # mysql中可以使用limit关键字
        if limit is not None:
            sql.append('limit')
            if isinstance(limit, int):   # 如果是int类型则增加占位符
                sql.append('?')
                args.append(limit)
            elif isinstance(limit, tuple) and len(limit) == 2:   # limit可以取2个参数，表示一个范围
                sql.append('?,?')
                args.extend(limit)
            else:       # 其他情况自然是语法问题
                raise ValueError('Invalid limit value: %s' % str(limit))
            # 在原来默认SQL语句后面再添加语句，要加个空格

        rs = yield from select(' '.join(sql), args)
        return [cls(**r) for r in rs]

    @classmethod
    @asyncio.coroutine
    def findNumber(cls, selectField, where=None, args=None):
        # 获取行数
        # 这里的 _num_ 什么意思？别名？ 我估计是mysql里面一个记录实时查询结果条数的变量
        sql = ['select %s _num_ from `%s`' % (selectField, cls.__table__)]
        # pdb.set_trace()
        if where:
            sql.append('where')
            sql.append(where)   # 这里不加空格？
        rs = yield from select(' '.join(sql), args, 1)  # size = 1
        if len(rs) == 0:  # 结果集为0的情况
            return None
        return rs[0]['_num_']   # 有结果则rs这个list中第一个词典元素_num_这个key的value值

    @classmethod
    @asyncio.coroutine
    def find(cls, pk):
        # 根据主键查找
        # pk是dict对象
        rs = yield from select('%s where `%s`=?' % (cls.__select__, cls.__primary_key__), [pk], 1)
        if len(rs) == 0:
            return None
        return cls(**rs[0])

    # 这个是实例方法
    @asyncio.coroutine
    def save(self):
        # arg是保存所有Model实例属性和主键的list,使用getValueOrDefault方法的好处是保存默认值
        # 将自己的fields保存进去
        args = list(map(self.getValueOrDefault, self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        # pdb.set_trace()
        rows = yield from execute(self.__insert__, args)  # 使用默认插入函数
        if rows != 1:
            # 插入失败就是rows!=1
            logging.warning(
                'failed to insert record: affected rows: %s' % rows)

    @asyncio.coroutine
    def update(self):
        # 这里使用getValue说明只能更新那些已经存在的值，因此不能使用getValueOrDefault方法
        args = list(map(self.getValue, self.__fields__))
        args.append(self.getValue(self.__primary_key__))
        # pdb.set_trace()
        rows = yield from execute(self.__update__, args)    # args是属性的list
        if rows != 1:
            logging.warn(
                'failed to update by primary key: affected rows: %s' % rows)

    @asyncio.coroutine
    def remove(self):
        args = [self.getValue(self.__primary_key__)]
        # pdb.set_trace()
        rows = yield from execute(self.__delete__, args)
        if rows != 1:
            logging.warn(
                'failed to remove by primary key: affected rows: %s' % rows)

class Field(object):  # 属性的基类，给其他具体Model类继承

    def __init__(self, name, column_type, primary_key, default):
        self.name = name
        self.column_type = column_type
        self.primary_key = primary_key
        self.default = default 			# 如果存在default，在getValueOrDefault中会被用到

    def __str__(self):  # 直接print的时候定制输出信息为类名和列类型和列名
        return '<%s, %s:%s>' % (self.__class__.__name__, self.column_type, self.name)


class StringField(Field):

    def __init__(self, name=None, primary_key=False, default=None, ddl='varchar(100)'):
        # String一般不作为主键，所以默认False,DDL是数据定义语言，为了配合mysql，所以默认设定为100的长度
        super().__init__(name, ddl, primary_key, default)

class BooleanField(Field):

    def __init__(self, name=None, default=False):
        super().__init__(name, 'boolean', False, default)


class IntegerField(Field):

    def __init__(self, name=None, primary_key=False, default=0):
        super().__init__(name, 'biginit', primary_key, default)


class FloatField(Field):

    def __init__(self, name=None, primary_key=False, default=0.0):
        super().__init__(name, 'real', primargity_key, default)

class TextField(Field):

    def __init__(self, name=None, default=None):
        super().__init__(name, 'text', False, default)  # 这个是不能作为主键的对象，所以这里直接就设定成False了