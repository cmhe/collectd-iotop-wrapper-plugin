# collectd-iotop-wrapper-plugin

This is a simple plugin for [collectd](https://collectd.org/) to get system total statistics from [iotop](http://guichaz.free.fr/iotop/) by wrapping around it.

Its more of a quick&dirty hack to get around OpenVZ/Virtuozzo virtualized servers where access to proper block and file system statistics are not available.

Collectd plugin configuration:

```
LoadPlugin python
<Plugin python>
    ModulePath "/opt/collectd_plugins"
    Import "iotop_wrapper"
    <Module iotop_wrapper>
	    Interval 5
    </Module>
</Plugin>
```

Where 'Interval' is the duration parameter that gets in iotops '-d' option.
