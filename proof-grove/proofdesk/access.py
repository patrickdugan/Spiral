"""Opt-in bearer access for an HTTPS reverse proxy; no credential is public state."""
from dataclasses import dataclass, field
import hmac
import os
import re
from urllib.parse import urlsplit

from .domain import Refused


class AccessDenied(Refused):
    def __init__(self,code,status=403):
        self.status=status
        super().__init__(code)


@dataclass(frozen=True)
class HostedAccess:
    token:str=field(repr=False)
    origins:tuple[str,...]
    hosts:tuple[str,...]
    mutations:bool=False
    private_bundles:bool=False

    def __post_init__(self):
        if not re.fullmatch(r'[A-Za-z0-9_-]{43,128}',self.token):raise Refused('hosted_token_too_short_or_invalid')
        if not self.origins or not self.hosts:raise Refused('hosted_allowlist_required')
        for origin in self.origins:
            parsed=urlsplit(origin)
            if parsed.scheme!='https' or parsed.netloc!=origin[8:] or parsed.username or parsed.password or not parsed.hostname:
                raise Refused('hosted_https_origin_required')
        for host in self.hosts:
            if not re.fullmatch(r'[A-Za-z0-9.-]+(?::[0-9]{1,5})?',host):raise Refused('invalid_hosted_host')

    @classmethod
    def from_config(cls,config):
        if not isinstance(config,dict):raise Refused('hosted_access_configuration_required')
        return cls(os.environ[config['token_env']],tuple(config['allowed_origins']),tuple(config['public_hosts']),
                   config.get('allow_mutations') is True,config.get('allow_private_bundles') is True)

    def authorize(self,headers,path,mutation=False):
        values=headers.get_all('Authorization',[])
        expected='Bearer '+self.token
        if len(values)!=1 or not hmac.compare_digest(values[0].encode(),expected.encode()):
            raise AccessDenied('hosted_authentication_required',401)
        if path=='/api/ark/exits/bundle' and not self.private_bundles:
            raise AccessDenied('hosted_private_bundle_disabled')
        if mutation and path not in ('/api/proofs/check','/api/proofs/recorded/check') and not self.mutations:
            raise AccessDenied('hosted_mutations_disabled')
