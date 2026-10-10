A 27 billion parameter model running
locally on a single GPU should not be
able to compete with Frontier level
models like Claude Opus 4.6. But that is
exactly what I've been seeing with the
new Quen 3.827B.
Today I'm going to be testing it at
every single reasoning level, optimizing
the model for maximum speed in Unslaw
Studio Desktop, and then connecting the
exact same local model into the brand
new Deep Seek harness for agentic
coding. We'll start with testing the
different reasoning levels. Then towards
the end of the video, I'll be giving
Quen and Opus the same massive prompt to
build a Minecraft clone as somehow this
small model is beating Opus 4.6. 6 in
Claude Code. Now, really quick, I don't
Benchmarks
normally like to go over benchmarks for
too long in my videos, but this is an
absolutely amazing website. If you've
never checked this out before, this is
artificialanalysis.ai,
and they do an excellent job at
comparing the different models in every
single different model from every
company. And down here, I just want to
really quick show you guys, I added
Claude Opus 4.6 six with the max
reasoning level and it is actually
scoring lower in the intelligence index
[music] than Quen 3.827B 827B and then
coming down here this is another
artificial analysis index open weights
and same thing it is scoring lower if we
go to this about the same and then text
only about the same. So unbelievable
that we have a 27 billion parameter
model that we can run on local hardware
and generally affordable local hardware
as well. Is absolutely incredible that
we have a 27 billion parameter model
that is beating some models that are in
the trillions of parameters. Absolutely
insane. Now moving over to one of the
Unsloth Desktop Setup
programs that we're going to be using
today. This is Unslave Desktop. Now,
I've done videos in the past of how to
install Unsloth Studio. Unsloth Studio
also comes with Unsloth desktop, but
this is just the desktop app for
Windows. And I like this app over LM
Studio for specifically for Windows
because it automatically optimizes the
model to be almost the perfect weights
and all of the different settings so
that you can get the most out of the
model and optimal speeds. Whereas in LM
Studio, I was having issues with MTP
generation and different speculative
decoding issues as well in LM Studio.
So, if you're unfamiliar with Unsoft
Studio, check out my other video. But in
this video, I'm going to do a quick
rundown of how to install and get Quen
3.827B
running. Now, my system, I have a 5090
with 32 gigs of RAM. However, you should
be able to actually run Quen 3.8 8 with
a pretty decent context window with a
3090 or even a 4090 with 24 gigs of RAM
and there are even quants where you can
run this at 16 gigs of VRAM if you have
something like a 4080 or a 5080. So if
you go over here you can go to this
model hub and you can go ahead and find
Quen 3.827B.
Now, we're going to be using the
Unslaught version because this is the
best version that I personally know of.
They are always releasing new updates,
trying to optimize their different
quantization levels to make the model
the best that it can possibly be. So,
right here, I've actually downloaded a
few different models. Today I'm going to
be using the 4bit quant because I feel
like that's what a lot of people are
going to be able to run on their systems
just to show you guys what this model
can do even at a Q4 level [music] UD
quantization and UD stands for unslopped
dynamic. So essentially they are taking
some of the weights and trying to
optimize it for the maximum potential.
Model Settings
So once you've got the model installed,
you can go ahead and load it here. Now
let me just show you guys some of the
settings. There are a few settings that
I would recommend changing. So on the
right side here, context length. I'm
using a pretty healthy 133,000 context
length that fits really nicely into my
5090s VRAM. Now, if you're running with
24, you could probably actually get away
with this about the same context length.
You might have to pull it down to like
100K, but that should still be very
usable for what we're trying to achieve
today. Now right here, this is going to
be key. This is the KV cache DT type.
This is quanticizing the actual context
length. And we are using a Q8 because
that is where [music] you essentially
have lossless quality. You go any lower
than this, like Q4, your context window
is going to start deteriorating just a
little bit. However, Q4 is still very
usable if you're trying to just squeeze
a little bit more context window out of
your system. Now, a few other things to
change. This should automatically use
MTP with the auto setting. However, I
would just set MTP. And [music] then the
fastest I found so far with the draft
tokens is two. That's just telling the
MTP for speculative decoding how many it
should use. And then parallel slots, I
changed this to [music] one. And then
the only other settings that I would
recommend changing is down here. These
are the different settings that Unslave
recommends for a thinking model, which
is what I prefer to use. And then
[music] this is going to be very
important for the Deep Seek harness. I'm
essentially just maxing out the [music]
max tokens for the output length of
every single prompt so that it doesn't
run into any issues when we go over to
Deep Seek Harness a little bit later in
Qwen 3.8 Reasoning Level Testing
the video. So, running a few tests. I
just ran some tests in Unsllo Studio
itself. I just wanted to see what it
could do. And I'm essentially making a
Tetris clone. I'm giving it a pretty
simple prompt. [music] Make a Tetris
clone. And I'm doing it with no
reasoning, low reasoning, [music]
medium reasoning, and then extra high.
Those are the only reasoning levels that
are available in Quen 3.8 27B. Even
though there is a high level, you set it
to this high level, it's just going to
default to extra high in the Unsllo
Studio. Just got to stick to low,
medium, and extra high. So this is the
No Reasoning Test
test that I ran with no reasoning
involved and all I did was I added this
code which is pretty cool. This is
something that's included in the Unsloth
desktop app. So I am running this right
now just directly in Unsloth. That is
something you can do if you're not doing
any crazy coding tasks or you just need
a quick local model for some prompting.
You can easily just use this desktop
app. don't have to use the deep sea
carnage that we're going to be setting
up a little bit later in this video. So,
this is pretty interesting. I ran a
Tetris prompt. I just said create a
Tetris game in HTML
and I did it with no reasoning and it
went through and made all of this. I had
to try to ask it where the file was and
it finally figured out how to get me the
file. And here's some of the stats. This
was running at an average of 100 tokens
per second, which is unbelievable for
speeds for this quantization level and
that big of a context window. So, here's
the Tetris game that it ended up making
in HTML. And this is actually really
solid. It looks really good and it works
very well. So, this is with no reasoning
on. And this might be what you'll want
to default to when you're like
essentially doing some quick coding is
just turning off that reasoning.
However, I do like to test these with
the different reasoning levels just to
see what it can make. This is honestly a
pretty solid clone overall. Now, the one
that is the best was actually probably
the low quant. We're going to check that
one out in a second here, but this is
really, really solid for what it did.
And it is honestly pretty interesting
because this Quen model seems to really
take [music]
the effort to a whole another level.
Like I've seen less effort sometimes
from Opus, which is honestly crazy, than
this small model. Like it'll make sure
that it creates a really good
generation. And as you can see, this
honestly looks amazing with zero
reasoning on. Now, moving on to the low
Low Reasoning Test
reasoning level. This one was pretty
interesting. It ended up using almost
the entire context window, which is
crazy. first of all like 124k context
window. However, it made an absolutely
incredible Tetris game. It went through
and it took quite a while, but it was
running at a really nice 110 tokens per
second. And what it produced honestly
blew me away. Now, this is actually
nice. It gave me an HTML preview here.
So, I can just expand this and play it
right here, right in Unslaw Studio. This
one has the best graphics I've seen. It
looks better than the last generation.
And I think it even had a full animation
when the block or when the line breaks.
Let's go look here. [music]
So, let's get that line.
Yeah. See that animation right there?
So, this one, it spent like quite a long
time to build this. Like it probably
took 30 minutes, but it put every single
ounce of effort that it possibly could
into making this [music] Tetris clone.
And this might be one of the best Tetris
clones that I [music] have ever seen
with a local model. In fact, this
probably is the best Tetris clone I've
ever seen using a local model. Like even
better than some generations from Opus,
which is actually crazy. Now, moving on
Medium Reasoning Test
to the medium reasoning level. This one
was very interesting to me. It only used
10k of the context and it practically
built this entire game in less than 2
minutes. And also, the token speed was
unbelievably fast. 141.8 tokens. That's
the highest I've seen so far in any
generation I've tested. And as you can
see on the right here, it only took
about 39 seconds to create this
generation. So, I'm not sure if there's
something wrong with the reasoning level
with this specific version of the Unsllo
Quen 3.827B.
I know we're on version three now, but
it did actually end up making a Tetris
game here. And honestly, this one isn't
too bad. This is with the medium
reasoning, and it did the fastest
generation, and it still looks really
solid, and it works just as well. Oh,
let's see if we can get a line to
go here.
And yep, line disappears. It doesn't
have any nice graphics or anything, but
it still has the preview block down at
the bottom. It has the down. It has the
drop function. It has pretty much
everything a basic Tetris game would
have. And it's kind of actually crazy
that it generated this this quickly
using the medium reasoning level where I
would have expected the low to be much
faster. So there's something very
interesting with the medium versus low.
Low for some reason seems to be higher
reasoning level than medium for whatever
reason. I'm not really sure why that is.
Extra High Reasoning Test
And finally, we have the extra high
reasoning level. Now, this one used 60k
of the context window, and it created a
pretty decent Tetris game. However,
again, it's very interesting that the
low setting actually used more context
and reasoned for longer than the extra
high. And here we can see we got a
decent 99.2 tokens per second. All
right, and here's the generation for the
X high. And this one is interesting cuz
it looks very similar to the medium
generation. However, it took much longer
to create. It looks almost identical to
the medium generation. And one thing
that I notice is I cannot spin the
blocks more than one time. Now, let's
see if it'll let me spin it with the Z
and the X. Nope. Looks like you can only
spin the block one time. So, even this
one on the high reasoning level had all
kinds of issues. So, so far it looks
like low is the winner. If you want the
[music] fastest generation possible, you
got to go with medium. And then the no
reasoning one was also pretty decent.
But I'm still going to give low the win
here when it comes to the reasoning
levels. All right, so next thing is
Deepseek Harness
hooking this into Deep Seek Harness. And
this is pretty awesome. So essentially
what you've got here, you can go ahead
and install this pretty easily if you go
to their website and follow their
GitHub. And you can install this on
Windows and it uses essentially node in
order to install this Deep Seek harness
and you can use it in Windows or Mac. So
Deepseek Harness Setup
if you go to this models tab here, you
can go ahead and set up your Unslaw
Studio to connect to the Unslaw Studio
using your configured model. So in my
case, I have configured an API key in
the Unsllo Studio. I'll just show you
guys this real quick. You can go ahead
and go to Unsllo Studio. You go to the
API section. Go ahead and type in like
deep sea [music] harness for example.
I'll just say Deepc Carness 2 because
I've already set this up. [music] Create
a token. Generate that here. You'll copy
this token and you'll copy that here
into the API key. And then you can set
it up so it's fully locally. Just make
sure you point it to this address. By
default, Unsllo will use port 888 at v1
and then open AI chat completions and
then I have simply just set up this
model here. Now, unfortunately, right
now this isn't a developer preview. So,
getting to some of the settings is a
little tricky. So, you are going to have
to type in a specific command in your
PowerShell window in order to set up the
different reasoning levels. And that is
this command here, the notepad env user
profile.dnsh
settings yaml. And if we go to this,
I'll just really quick show you guys.
These are the settings that you want to
use with the Quen 3.827B
model. It essentially tells it, hey, I
want you to use these reasoning effort
levels, low, medium, and extra high,
which is the ones that are embedded into
Quinn 3.827B.
I'm giving it my max context window and
then max tokens. And then also you want
to make sure you use this input here and
do text and image. Otherwise, it's not
going to be able to use the vision
portion of the Quen 3.827B.
I'll put those two commands in the
description below so you guys can just
copy all the settings and get to that
settings menu pretty quickly. Now,
How To Use Deepseek Harness
moving on to this Deep Sea Caress. This
is a really cool program. A lot of
people say it's kind of like clawed
code, but I think it's more like codecs
where you can have a workspace area or a
project and then you have chats that you
can have underneath it and you can start
new chats underneath that just like
codeex. So right here I have a couple
examples. I did another Tetris test
using the Deep Seek harness just to test
it out and I did it with the low effort
level. It went through and created the
full Tetris game. Now, there were a few
problems like it was cutting off at the
top and I had to fix that. And then I
had to essentially reenter it down here
and it did create a pretty nice looking
game here. Let's just do a quick test.
This is your Tetris clone here. And it
looks pretty good, pretty solid.
Everything works good. It actually has
nice line animations as you can see
there.
And everything works. And yep. So,
pretty solid. and it's fully centered on
the screen. Now, that was a problem. It
was like centered over here. So, that is
the one thing I have noticed with the
Deep Seek harness. You do kind of have
to go back and forth with it just a
little bit, but that's similar to like
things like Codeex or Claude Code where
you just have to go back and forth with
it and tell it to fix certain things.
So, to set this up, this is actually
pretty cool. You can say add workspace
here and then down at the bottom, it's
actually going to load a node. So node
program and then you have to go in it
and define what your folder is just like
claude code just like codeex. So I could
do like uh just test folder here and
then right now we have a new workspace
and I could tell it something like I do
just do a quick example create a notepad
app and it's going to go through and
it's going to connect to [music] our
unsllo studio here which you can even
open up this full API window fully
monitor what it's doing all of its tool
calls and everything coming from the
unsloth studio. And if we go back to the
deep sea harness, we can see it's going
through the full thinking process,
trying to decide what it wants to do
first, thinking about the empty
directory that I gave it. It's a pretty
broad prompt, so I'm actually kind of
curious to see what this will do. All
right, and did that really quickly. I
guess I didn't give it a whole lot of
instructions, but it built this Notepad
HTML. Let's go ahead and see what this
built for us here. All right. So, just
built a pretty basic notes app, which is
interesting. Kind of cool. Untitled
note. Let's just call it notes test. I
don't really expect this to work very
well cuz we didn't really give it a
whole lot to work with here. This is
pretty cool. It literally built this in
a matter of like 30 seconds in Deep Seek
Harness. So, that was just an example I
was going to show you guys on how to get
your different projects set up. However,
with the right prompting and the correct
harness, you can build some pretty cool
things. So, let me just show you guys
The Coding Challenge: Qwen 3.8 vs Claude Opus
what I built here. This is one of my
prompts that I've been working on for a
very long time. I'll provide this prompt
in a link in the description. If you
guys are familiar with my videos, I like
to share all my prompts with you guys.
But, this is the full Minecraft prompt
that I have been slowly developing and
making better and better for the sake of
doing my testing. And what it built is
honestly pretty crazy. So, the first run
through it actually built a [music]
Minecraft clone that was playable and
working. Like, I wasn't even expecting
it to be fully playable at all. And it
actually was. Now, I have kind of been
messing around with this. I've been
going back and forth with it, back and
forth with different things like like
making the animals look accurate,
different things like that. And it's
gone through and it's fixed pretty much
everything I've asked it to do. And I
haven't made too many changes here.
Essentially, I just changed like the
night cycle and pretty much the animals
and I made the zombies and everything
more like realistic and functional. But
that's about all the different prompts
that I've changed so far with this whole
thing. And it created this file that is
just an HTML file that we can run in our
Qwen3.8 27B - Minecraft Clone
browser here. And honestly, this blew me
away. I was running this and I was like,
"Wow, [music] this is absolutely crazy."
Like, it's got different like crevices,
like cave system. It's even got a full
crafting system. [music]
And it was running at a really decent
speed, too. Like about like
120 tokens per second or so. It's even
got like big mountains, nice rivers. the
like water works where you can like go
up and down in the water. It's even got
like a hold so you can see like the
block that you're holding. The one thing
there's a few bugs like right here. I
can't jump out of the water if I don't
put a block there and the water doesn't
fill in. But that is pretty normal for
these generations. So this is on par
with one of the generations that I built
with Fable and also Opus 5, which I just
thought was absolutely crazy. And like
check this out. It's got like a full
crafting system. So, if we go find like
a tree here.
The only thing that I think needs a
little fixing with this is it takes a
very long time to break the wood blocks.
So, I'm going to speed this up and just
come back so we can show you guys the
full crafting.
All right. So, back in the game here, if
I grab my wood blocks and place them
here, it's actually going to create the
wood. And then we do four here. And is
literally created a crafting bench,
which just blew me absolutely away. And
I can set it too. So I can set it here.
And then I can go into the actual
crafting and create different tools like
sticks. So it's got like a full crafting
system. Let's see if it'll actually even
make the pickaxe here. Let's see if I
can remember this. Yep. Oh, wow. So it
created the pickaxe. And now we have a
pickaxe. And you can actually like see
it in my hand. I mean, it's not the best
animation in the world, but it does work
as a pickaxe. And you can see that the
blocks are now cracking and breaking way
faster. So, it is working, which is
actually crazy that I have a working
tool system. And that this fully
generated that, too, by the way. And
look how great this looks, too. Like, it
did a really good job. And it's
essentially an endless world, full
generation. And it even has a full night
cycle and zombies and everything that
come out at night.
So, pretty cool. And let me just speed
it up so I can show you guys the night
cycle as well here. All right, so the
sun's starting to go down. It's starting
to be night time here. And you can see
that there are now zombies that have
essentially spawned.
And wow. [laughter]
Okay. Well, we got him. But yeah, it's
got actual zombies that are essentially
going to hurt you. It even has the
creepers. Uh-oh. Just fell into like a
cavern here. That's no good. Oh, there's
the explosion. The creeper. So, it's got
like explosions and everything. You can
see the block animations, too. Like some
generations don't even create this like
floating block animation when it like
creates or breaks a block I should say.
And yeah, so right now we're in pretty
hostile territory here. There is quite a
few. That's one thing I noticed with
this generation. It created quite a few
different zombies. But just the fact
that it is a almost [music] nearly
playable Minecraft game with some tweaks
just honestly blew my mind. Like this is
just so cool that a local model is able
to create this kind of generation that
something like even Fable 5 is creating
something similar in this regard. Like
pretty crazy. Let's see if that'll get
me. Oh, almost. [laughter]
Wow. So anyway, let's go ahead and check
out now the Opus generation, which I was
not impressed with at all. I don't know
if they [music] have essentially nerfed
the Opus one, but it was pretty bad. So,
let's go check that out real quick here.
Opus 4.6 - Minecraft Clone
So, this is the Opus generation here.
And this is honestly one of the worst
Minecraft experiences, worst Minecraft
clones I have ever seen in my entire
life. Now, to be fair, I did use the
exact same prompt and I did use Opus
with low reasoning. However, I was just
trying to match what Quen 3.827B
would also be using. So, I used both of
them with low reasoning effort. And I
don't even know what this is. Like this
is honestly like one of the worst
Minecraft clones. Probably actually the
worst Minecraft clone I've ever seen.
Like I'm not even sure what I'm looking
at here. So I went back into the chat. I
was trying to give it the benefit of the
doubt and I said, "Okay, it finally
loaded. However, this is one of the
worst Minecraft clones I've ever seen."
And it actually came back and it tried
to fix it. It actually did a decent job.
It went through and thought for like
about 8 minutes. But the first one that
it did with that massive prompt, it only
thought for like three minutes. [music]
So I guess low reasoning effort is
actually very low when it comes to opus.
So this is what the revised version
[music]
created for me. Now to be fair, I will
say the graphics look pretty solid. Like
the graphics are not too bad. You can
actually jump out of the like water
area. The graphics look really good.
However, there is quite a few problems
with this generation. So, first of all,
I was testing out the crafting system.
So, and also, okay, this is the first
thing I noticed. Look at these blocks
that are floating. Like, what even is
that? That looks awful. I don't even
know what that is. [music] So, I was
trying to get the crafting to work and I
couldn't even get it to work. So, I got,
you know, the first wood blocks, went to
my crafting window. First of all, I was
trying to figure out how to place these.
I don't know know where it even went.
[music] So, it guess went to storage
here and then I tried to go and do this
and so far
it is not even understanding to make
wood. Oh, there we go. It actually did
work to make wood. However, I can't like
grab it. So, let's see if I go out of
this menu here. And yeah, [music] like I
can't even pull it out of the crafting
inventory. So regardless of this really
funky animation, it still does not work.
I cannot get this to actually generate
or pull
from that storage. So the storage and
the crafting essentially don't work at
all. I'm trying to click on this. I'm
left clicking on it. Like I don't know
how to grab these actual wood blocks.
So, the crafting system is broken. Um,
this is another thing I noticed is when
I hit the escape button, it brings up
that menu. And then this is one of the
worst things with this that I noticed is
the water. Let me see if I can find some
better area before it gets [music] too
dark here. And we get like some zombies
coming out. Also, the night cycle is
like really fast. Okay, here we go. This
is a good example. If I jump into this
water, you can see I'm not floating.
like it shows water on top, but I can't
float up. See, I'm just jumping
underwater. So, there's no water
physics. So, that's another thing. And
honestly, like I [music] said, the
graphics do look pretty good. Like,
arguably better than the [music] Quen
3.827B.
But honestly, I'm giving Quen 3.827B
827B the win here because it is actually
more functional Minecraft than this.
Like I don't even know what this is.
What kind of zombie is this? If you look
at the side, well, it's kind of hard to
see, but it's a fourlegged like like
horse zombie. Like even this doesn't
even look accurate to like the original.
If I can actually get it there. There we
go. And yeah, also you notice that they
are able to walk underwater just like
me. So, and then trying to get out of
here is a pain because there's no way to
float. So, you got to like kind of make
your way up. And yeah, pretty much
overall not very impressed with the Opus
4.6 generation. Now, it did do this much
faster, but it is on, you know, Frontier
hardware. We are running this on a 5090
with Quen 3.827B.
Verdict
So overall, I would say, like I said,
Quan 3.827B
wins in this test, which is absolutely
crazy that a small local model is
beating frontier level models from
Enthropic as well as Open AI. So anyway,
that'll do it for this video. If you
guys have any questions, let me know
down below in the comments. I plan on
going over some more local AI content.
I'm also got a video planned on using
Grockbot because I just stumbled across
that today and I think it looks really
cool. It has a lot of really cool
potential. So stick around, stay tuned
for that video. Subscribe to the channel

