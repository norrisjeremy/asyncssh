# Copyright (c) 2020 by Ron Frederick <ronf@timeheart.net> and others.
#
# This program and the accompanying materials are made available under
# the terms of the Eclipse Public License v2.0 which accompanies this
# distribution and is available at:
#
#     http://www.eclipse.org/legal/epl-2.0/
#
# This program may also be made available under the following secondary
# licenses when the conditions for such availability set forth in the
# Eclipse Public License v2.0 are satisfied:
#
#    GNU General Public License, Version 2.0, or any later versions of
#    that license
#
# SPDX-License-Identifier: EPL-2.0 OR GPL-2.0-or-later
#
# Contributors:
#     Ron Frederick - initial implementation, API, and documentation

"""Unit tests for parsing OpenSSH-compatible config file"""

import os
import socket
import unittest

from pathlib import Path
from unittest.mock import patch

import asyncssh

from asyncssh.config import load_client_config, load_server_config

from .util import TempDirTestCase


class _TestConfig(TempDirTestCase):
    """Unit tests for config module"""

    def _load_config(self, config_paths):
        """Abstract method to load a config object"""

        raise NotImplementedError

    def _parse_config(self, config_data, **kwargs):
        """Return a config object based on the specified data"""

        with open('config', 'w') as f:
            f.write(config_data)

        return self._load_config('config', **kwargs)

    def test_blank__and_comment(self):
        """Test blank and comment lines"""

        config = self._parse_config('\n#Port 22')
        self.assertIsNone(config.get('Port'))

    def test_set_bool(self):
        """Test boolean config option"""

        for value, result in (('yes', True), ('true', True),
                              ('no', False), ('false', False)):
            config = self._parse_config('Compression %s' % value)
            self.assertEqual(config.get('Compression'), result)

        config = self._parse_config('Compression yes\nCompression no')
        self.assertEqual(config.get('Compression'), True)

    def test_set_int(self):
        """Test integer config option"""

        config = self._parse_config('Port 1')
        self.assertEqual(config.get('Port'), 1)

        config = self._parse_config('Port 1\nPort 2')
        self.assertEqual(config.get('Port'), 1)

    def test_set_string(self):
        """Test string config option"""

        config = self._parse_config('BindAddress addr')
        self.assertEqual(config.get('BindAddress'), 'addr')

        config = self._parse_config('BindAddress addr1\nBindAddress addr2')
        self.assertEqual(config.get('BindAddress'), 'addr1')

        config = self._parse_config('BindAddress none')
        self.assertIsNone(config.get('BindAddress', ()))

    def test_set_address_family(self):
        """Test address family config option"""

        for family, result in (('any', socket.AF_UNSPEC),
                               ('inet', socket.AF_INET),
                               ('inet6', socket.AF_INET6)):
            config = self._parse_config('AddressFamily %s' % family)
            self.assertEqual(config.get('AddressFamily'), result)

        config = self._parse_config('AddressFamily inet\n'
                                    'AddressFamily inet6')
        self.assertEqual(config.get('AddressFamily'), socket.AF_INET)

    def test_set_rekey_limit(self):
        """Test rekey limit config option"""

        for value, result in (('1', ('1', ())),
                              ('1 2', ('1', '2')),
                              ('1 none', ('1', None)),
                              ('default', ((), ())),
                              ('default 2', ((), '2')),
                              ('default none', ((), None))):
            config = self._parse_config('RekeyLimit %s' % value)
            self.assertEqual(config.get('RekeyLimit'), result)

        config = self._parse_config('RekeyLimit 1 2\nRekeyLimit 3 4')
        self.assertEqual(config.get('RekeyLimit'), ('1', '2'))

    def test_get_compression_algs(self):
        """Test getting compression algorithms"""

        config = self._parse_config('Compression yes')
        self.assertEqual(config.get_compression_algs(),
                         'zlib@openssh.com,zlib,none')

        config = self._parse_config('Compression no')
        self.assertEqual(config.get_compression_algs(),
                         'none,zlib@openssh.com,zlib')

        config = self._parse_config('')
        self.assertEqual(config.get_compression_algs('default'), 'default')

    def test_include(self):
        """Test include config option"""

        with open('include', 'w') as f:
            f.write('Port 2222')

        for path in ('include', Path('include').absolute().as_posix()):
            config = self._parse_config('Include %s' % path)
            self.assertEqual(config.get('Port'), 2222)

    def test_match_all(self):
        """Test a match block which always matches"""

        config = self._parse_config('Match all\nPort 2222')
        self.assertEqual(config.get('Port'), 2222)

    def test_config_disabled(self):
        """Test config loading being disabled"""

        self._load_config(None)

    def test_config_list(self):
        """Test reading multiple config files"""

        with open('config1', 'w') as f:
            f.write('BindAddress addr')

        with open('config2', 'w') as f:
            f.write('Port 2222')

        config = self._load_config(['config1', 'config2'])
        self.assertEqual(config.get('BindAddress'), 'addr')
        self.assertEqual(config.get('Port'), 2222)

    def test_unknown(self):
        """Test unknown config option"""

        config = self._parse_config('XXX')
        self.assertIsNone(config.get('XXX'))

    def test_errors(self):
        """Test config errors"""

        for desc, config_data in (
                ('Missing value', 'AddressFamily'),
                ('Unbalanced quotes', 'BindAddress "foo'),
                ('Extra data at end', 'BindAddress foo bar'),
                ('Invalid address family', 'AddressFamily xxx'),
                ('Invalid boolean', 'Compression xxx'),
                ('Invalid integer', 'Port xxx'),
                ('Invalid match condition', 'Match xxx')):
            with self.subTest(desc):
                with self.assertRaises(asyncssh.ConfigParseError):
                    self._parse_config(config_data)


class _TestClientConfig(_TestConfig):
    """Unit tests for client config objects"""

    def _load_config(self, config_paths, local_user='user', user=(),
                     host='host', port=()):
        """Load a client configuration"""

        # pylint: disable=arguments-differ

        return load_client_config(local_user, user, host, port, config_paths)

    def test_append_string(self):
        """Test appending a string config option to a list"""

        config = self._parse_config('IdentityFile foo\nIdentityFile bar')
        self.assertEqual(config.get('IdentityFile'), ['foo', 'bar'])

        config = self._parse_config('IdentityFile foo\nIdentityFile none')
        self.assertEqual(config.get('IdentityFile'), ['foo'])

        config = self._parse_config('IdentityFile none')
        self.assertEqual(config.get('IdentityFile'), [])

    def test_set_string_list(self):
        """Test string list config option"""

        config = self._parse_config('UserKnownHostsFile file1 file2')
        self.assertEqual(config.get('UserKnownHostsFile'), ['file1', 'file2'])

        config = self._parse_config('UserKnownHostsFile file1\n'
                                    'UserKnownHostsFile file2')
        self.assertEqual(config.get('UserKnownHostsFile'), ['file1'])

    def test_append_string_list(self):
        """Test appending multiple string config options to a list"""

        config = self._parse_config('SendEnv foo\nSendEnv  bar baz')
        self.assertEqual(config.get('SendEnv'), ['foo', 'bar', 'baz'])

    def test_set_remote_command(self):
        """Test setting a remote command"""

        config = self._parse_config('    RemoteCommand     foo  bar  baz')
        self.assertEqual(config.get('RemoteCommand'), 'foo  bar  baz')

    def test_set_and_match_hostname(self):
        """Test setting and matching hostname"""

        config = self._parse_config('Host host\n'
                                    '  Hostname new%h\n'
                                    'Match originalhost host\n'
                                    '  BindAddress addr\n'
                                    'Match host host\n'
                                    '  Port 1111\n'
                                    'Match host newhost\n'
                                    '  Hostname newhost2\n'
                                    '  Port 2222')

        self.assertEqual(config.get('Hostname'), 'newhost')
        self.assertEqual(config.get('BindAddress'), 'addr')
        self.assertEqual(config.get('Port'), 2222)

    def test_set_and_match_user(self):
        """Test setting and matching user"""

        config = self._parse_config('User newuser\n'
                                    'Match localuser user\n'
                                    '  BindAddress addr\n'
                                    'Match user user\n'
                                    '  Port 1111\n'
                                    'Match user new*\n'
                                    '  User newuser2\n'
                                    '  Port 2222')

        self.assertEqual(config.get('User'), 'newuser')
        self.assertEqual(config.get('BindAddress'), 'addr')
        self.assertEqual(config.get('Port'), 2222)

    def test_port_already_set(self):
        """Test that port is ignored if set outside of the config"""

        config = self._parse_config('Port 2222', port=22)

        self.assertIsNone(config.get('Port'))

    def test_user_already_set(self):
        """Test that user is ignored if set outside of the config"""

        config = self._parse_config('User newuser', user='user')

        self.assertIsNone(config.get('User'))

    def test_percent_expansion(self):
        """Test token percent expansion"""

        def mock_gethostname():
            """Return a static local hostname for testing"""

            return 'thishost.local'

        def mock_home():
            """Return a static local home directory"""

            return '/home/user'

        with patch('socket.gethostname', mock_gethostname):
            with patch('pathlib.Path.home', mock_home):
                config = self._parse_config(
                    'Hostname newhost\n'
                    'User newuser\n'
                    'Port 2222\n'
                    'RemoteCommand %% %C %d %h %L %l %n %p %r %u')

        self.assertEqual(config.get('RemoteCommand'),
                         '% 98625d1ca14854f2cdc34268f2afcad5237e2d9d '
                         '/home/user newhost thishost thishost.local '
                         'host 2222 newuser user')

    @unittest.skipUnless(hasattr(os, 'getuid'), 'UID not available')
    def test_uid_percent_expansion(self):
        """Test UID token percent expansion where available"""

        def mock_getuid():
            """Return a static local UID"""

            return 123

        with patch('os.getuid', mock_getuid):
            config = self._parse_config('RemoteCommand %i')

        self.assertEqual(config.get('RemoteCommand'), '123')

    def test_missing_match_pattern(self):
        """Test match with a missing pattern"""

        with self.assertRaises(asyncssh.ConfigParseError):
            self._parse_config('Match host')

    def test_invalid_percent_expansion(self):
        """Test invalid percent expansion"""

        for desc, config_data in (
                ('Bad token in hostname', 'Hostname %p'),
                ('Invalid token', 'IdentityFile %x'),
                ('Percent at end', 'IdentityFile %')):
            with self.subTest(desc):
                with self.assertRaises(asyncssh.ConfigParseError):
                    self._parse_config(config_data)

class _TestServerConfig(_TestConfig):
    """Unit tests for server config objects"""

    def _load_config(self, config_paths):
        """Load a server configuration"""

        return load_server_config(config_paths)


del _TestConfig