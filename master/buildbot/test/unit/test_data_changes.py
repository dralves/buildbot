# This file is part of Buildbot.  Buildbot is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation, version 2.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Copyright Buildbot Team Members

import mock
from twisted.trial import unittest
from twisted.internet import defer, task
from buildbot.data import changes, exceptions
from buildbot.test.util import validation, endpoint
from buildbot.test.fake import fakedb, fakemaster
from buildbot.process.users import users

class Change(endpoint.EndpointMixin, unittest.TestCase):

    endpointClass = changes.ChangeEndpoint

    def setUp(self):
        self.setUpEndpoint()
        self.db.insertTestData([
            fakedb.SourceStamp(id=234),
            fakedb.Change(changeid=13, branch=u'trunk', revision=u'9283',
                            repository=u'svn://...', codebase=u'cbsvn',
                            project=u'world-domination', sourcestampid=234),
        ])


    def tearDown(self):
        self.tearDownEndpoint()


    def test_get_existing(self):
        d = self.callGet(dict(), dict(changeid=13))
        @d.addCallback
        def check(change):
            validation.verifyData(self, 'change', {}, change)
            self.assertEqual(change['project'], 'world-domination')
        return d


    def test_get_missing(self):
        d = self.callGet(dict(), dict(changeid=99))
        @d.addCallback
        def check(change):
            self.assertEqual(change, None)
        return d


class Changes(endpoint.EndpointMixin, unittest.TestCase):

    endpointClass = changes.ChangesEndpoint

    def setUp(self):
        self.setUpEndpoint()
        self.db.insertTestData([
            fakedb.SourceStamp(id=133),
            fakedb.Change(changeid=13, branch=u'trunk', revision=u'9283',
                            repository=u'svn://...', codebase=u'cbsvn',
                            project=u'world-domination', sourcestampid=133),
            fakedb.SourceStamp(id=144),
            fakedb.Change(changeid=14, branch=u'devel', revision=u'9284',
                            repository=u'svn://...', codebase=u'cbsvn',
                            project=u'world-domination', sourcestampid=144),
        ])


    def tearDown(self):
        self.tearDownEndpoint()

    def test_get(self):
        d = self.callGet(dict(), dict())
        @d.addCallback
        def check(changes):
            validation.verifyData(self, 'change', {}, changes[0])
            self.assertEqual(changes[0]['changeid'], 13)
            validation.verifyData(self, 'change', {}, changes[1])
            self.assertEqual(changes[1]['changeid'], 14)
        return d

    def test_get_fewer(self):
        d = self.callGet(dict(count='1'), dict())
        @d.addCallback
        def check(changes):
            self.assertEqual(len(changes), 1)
            validation.verifyData(self, 'change', {}, changes[0])
            self.assertEqual(changes[0]['changeid'], 13)
        return d
    def test_get_paging(self):
        d = self.callGet(dict(count='1',start=1), dict())
        @d.addCallback
        def check(changes):
            self.assertEqual(len(changes), 1)
            validation.verifyData(self, 'change', {}, changes[0])
            self.assertEqual(changes[0]['changeid'], 14)
        return d

    def test_get_invalid_count(self):
        d = self.callGet(dict(count='ten'), dict())
        self.assertFailure(d, exceptions.InvalidOptionException)

    def test_get_invalid_count2(self):
        d = self.callGet(dict(count=50000), dict())
        self.assertFailure(d, exceptions.InvalidOptionException)

    def test_get_sorted(self):
        # invert the default order
        d = self.callGet(dict(sort=[('changeid',1)]), dict())
        @d.addCallback
        def check(changes):
            validation.verifyData(self, 'change', {}, changes[1])
            self.assertEqual(changes[1]['changeid'], 13)
            validation.verifyData(self, 'change', {}, changes[0])
            self.assertEqual(changes[0]['changeid'], 14)
        return d

    def test_startConsuming(self):
        self.callStartConsuming({}, {},
                expected_filter=('change', None, 'new'))


class ChangeResourceType(unittest.TestCase):

    def setUp(self):
        self.master = fakemaster.make_master(wantMq=True, wantDb=True,
                                            wantData=True, testcase=self)
        self.rtype = changes.ChangeResourceType(self.master)

    def do_test_addChange(self, kwargs,
            expectedRoutingKey, expectedMessage, expectedRow,
            expectedChangeUsers=[]):
        clock = task.Clock()
        clock.advance(10000000)
        d = self.rtype.addChange(_reactor=clock, **kwargs)
        def check(changeid):
            self.assertEqual(changeid, 500)
            # check the correct message was received
            self.master.mq.assertProductions([
                ( expectedRoutingKey, expectedMessage),
            ])
            # and that the correct data was inserted into the db
            self.master.db.changes.assertChange(500, expectedRow)
            self.master.db.changes.assertChangeUsers(500, expectedChangeUsers)
        d.addCallback(check)
        return d

    def test_addChange(self):
        # src and codebase are default here
        kwargs = dict(author=u'warner', branch=u'warnerdb',
                category=u'devel', comments=u'fix whitespace',
                files=[u'master/buildbot/__init__.py'],
                project=u'Buildbot', repository=u'git://warner',
                revision=u'0e92a098b', revlink=u'http://warner/0e92a098b',
                when_timestamp=256738404,
                properties={u'foo': 20})
        expectedRoutingKey = ('change', '500', 'new')
        expectedMessage = {
            'author': u'warner',
            'branch': u'warnerdb',
            'category': u'devel',
            'codebase': u'',
            'comments': u'fix whitespace',
            'changeid' : 500,
            'files': [u'master/buildbot/__init__.py'],
            'project': u'Buildbot',
            'properties': {u'foo': (20, u'Change')},
            'repository': u'git://warner',
            'revision': u'0e92a098b',
            'revlink': u'http://warner/0e92a098b',
            'when_timestamp': 256738404,
            'sourcestamp': {
                'branch': u'warnerdb',
                'codebase': u'',
                'patch': None,
                'project': u'Buildbot',
                'repository': u'git://warner',
                'revision': u'0e92a098b',
                'created_at': 10000000,
                'ssid': 100,
            },
            # uid
        }
        expectedRow = fakedb.Change(
            changeid=500,
            author='warner',
            comments='fix whitespace',
            branch='warnerdb',
            revision='0e92a098b',
            revlink='http://warner/0e92a098b',
            when_timestamp=256738404,
            category='devel',
            repository='git://warner',
            codebase='',
            project='Buildbot',
            sourcestampid=100,
        )
        return self.do_test_addChange(kwargs,
                expectedRoutingKey, expectedMessage, expectedRow)

    def test_addChange_src_codebase(self):
        createUserObject = mock.Mock(spec=users.createUserObject)
        createUserObject.return_value = defer.succeed(123)
        self.patch(users, 'createUserObject', createUserObject)
        kwargs = dict(author=u'warner', branch=u'warnerdb',
                category=u'devel', comments=u'fix whitespace',
                files=[u'master/buildbot/__init__.py'],
                project=u'Buildbot', repository=u'git://warner',
                revision=u'0e92a098b', revlink=u'http://warner/0e92a098b',
                when_timestamp=256738404,
                properties={u'foo' : 20}, src=u'git', codebase=u'cb')
        expectedRoutingKey = ('change', '500', 'new')
        expectedMessage = {
            'author': u'warner',
            'branch': u'warnerdb',
            'category': u'devel',
            'codebase': u'cb',
            'comments': u'fix whitespace',
            'changeid' : 500,
            'files': [u'master/buildbot/__init__.py'],
            'project': u'Buildbot',
            'properties': {u'foo': (20, u'Change')},
            'repository': u'git://warner',
            'revision': u'0e92a098b',
            'revlink': u'http://warner/0e92a098b',
            'when_timestamp': 256738404,
            'sourcestamp': {
                'branch': u'warnerdb',
                'codebase': u'cb',
                'patch': None,
                'project': u'Buildbot',
                'repository': u'git://warner',
                'revision': u'0e92a098b',
                'created_at': 10000000,
                'ssid': 100,
            },
            # uid
        }
        expectedRow = fakedb.Change(
            changeid=500,
            author='warner',
            comments='fix whitespace',
            branch='warnerdb',
            revision='0e92a098b',
            revlink='http://warner/0e92a098b',
            when_timestamp=256738404,
            category='devel',
            repository='git://warner',
            codebase='cb',
            project='Buildbot',
            sourcestampid=100,
        )
        d = self.do_test_addChange(kwargs,
                expectedRoutingKey, expectedMessage, expectedRow,
                expectedChangeUsers=[123])
        @d.addCallback
        def check(_):
            createUserObject.assert_called_once_with(
                    self.master, 'warner', 'git')
        return d

    def test_addChange_src_codebaseGenerator(self):
        self.master.config = mock.Mock(name='master.config')
        self.master.config.codebaseGenerator = \
                lambda change : 'cb-%s' % change['category']
        kwargs = dict(author=u'warner', branch=u'warnerdb',
                category=u'devel', comments=u'fix whitespace',
                files=[u'master/buildbot/__init__.py'],
                project=u'Buildbot', repository=u'git://warner',
                revision=u'0e92a098b', revlink=u'http://warner/0e92a098b',
                when_timestamp=256738404,
                properties={u'foo' : 20})
        expectedRoutingKey = ('change', '500', 'new')
        expectedMessage = {
            'author': u'warner',
            'branch': u'warnerdb',
            'category': u'devel',
            'codebase': u'cb-devel',
            'comments': u'fix whitespace',
            'changeid' : 500,
            'files': [u'master/buildbot/__init__.py'],
            'project': u'Buildbot',
            'properties': {u'foo': (20, u'Change')},
            'repository': u'git://warner',
            'revision': u'0e92a098b',
            'revlink': u'http://warner/0e92a098b',
            'when_timestamp': 256738404,
            'sourcestamp': {
                'branch': u'warnerdb',
                'codebase': u'cb-devel',
                'patch': None,
                'project': u'Buildbot',
                'repository': u'git://warner',
                'revision': u'0e92a098b',
                'created_at': 10000000,
                'ssid': 100,
            },
            # uid
        }
        expectedRow = fakedb.Change(
            changeid=500,
            author='warner',
            comments='fix whitespace',
            branch='warnerdb',
            revision='0e92a098b',
            revlink='http://warner/0e92a098b',
            when_timestamp=256738404,
            category='devel',
            repository='git://warner',
            codebase='cb-devel',
            project='Buildbot',
            sourcestampid=100,
        )
        return self.do_test_addChange(kwargs,
                expectedRoutingKey, expectedMessage, expectedRow)

