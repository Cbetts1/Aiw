"""
AIM WWW Bridge — publish AIM content to the traditional World Wide Web.

This module provides two capabilities:
1. ``start_www_server`` — start the AIM web bridge on standard HTTP port 80
   (the same server as ``aim web start``, configured for port 80 by default).
2. ``publish_static_site`` — snapshot the AIM static pages and any content
   from a running AIM web bridge into a self-contained directory that can be
   deployed to any traditional web host (GitHub Pages, nginx, Apache, etc.)
   without external dependencies.
"""
