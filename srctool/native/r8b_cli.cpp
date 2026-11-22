// r8b_cli.cpp — r8brain-free 命令行封装（多声道 + 全旋钮）
// 用法: r8b <in_rate> <out_rate> <in.f64> <out.f64> [q] [transband] [atten] [phase] [channels]
//   q         0=16bit(att默认136.45) 1=24bit(180.15) 2=full(206.91)；显式给 atten 时以 atten 为准
//   transband 过渡带宽，占 Nyquist 的百分比 (0.5-45)
//   atten     阻带衰减 dB (40-260)；-1 表示用 q 的默认值
//   phase     0=linear 1=minimum
//   channels  交错声道数 (默认 1)
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <cmath>
#include "CDSPResampler.h"

int main( int argc, char* argv[] )
{
	if( argc < 5 )
	{
		fprintf( stderr,
			"usage: r8b in_rate out_rate in.f64 out.f64 [q 0=16 1=24 2=full]"
			" [transband%%] [atten dB or -1] [phase 0=lin 1=min] [channels]\n" );
		return 1;
	}

	const double InSR  = atof( argv[ 1 ] );
	const double OutSR = atof( argv[ 2 ] );
	const int    Q     = ( argc > 5  ? atoi( argv[ 5 ] ) : 2 );
	const double TB    = ( argc > 6  ? atof( argv[ 6 ] ) : 2.0 );
	double       ATT   = ( argc > 7  ? atof( argv[ 7 ] ) : -1.0 );
	const int    PH    = ( argc > 8  ? atoi( argv[ 8 ] ) : 0 );
	const int    NCH   = ( argc > 9  ? atoi( argv[ 9 ] ) : 1 );

	if( NCH < 1 || NCH > 64 ) { fprintf( stderr, "bad channel count\n" ); return 1; }
	if( TB <= 0.0 || TB > 45.0 ) { fprintf( stderr, "transband out of range\n" ); return 1; }
	if( ATT < 0.0 )
	{
		ATT = ( Q == 0 ? 136.45 : ( Q == 1 ? 180.15 : 206.91 ) );
	}
	if( ATT < 40.0 || ATT > 260.0 ) { fprintf( stderr, "atten out of range\n" ); return 1; }

	FILE* f = fopen( argv[ 3 ], "rb" );
	if( f == NULL ) { fprintf( stderr, "cannot open input\n" ); return 1; }
	fseek( f, 0, SEEK_END );
	const long long bytes = ftell( f );
	fseek( f, 0, SEEK_SET );
	const size_t total = (size_t) ( bytes / 8 );
	if( total % (size_t) NCH != 0 )
	{
		fprintf( stderr, "input sample count not divisible by channels\n" );
		fclose( f );
		return 1;
	}
	const size_t nframes = total / (size_t) NCH;
	std::vector< double > in( total );
	if( fread( in.data(), 8, total, f ) != total ) { fprintf( stderr, "read error\n" ); fclose( f ); return 1; }
	fclose( f );

	const r8b::EDSPFilterPhaseResponse phase =
		( PH == 1 ? r8b::fprMinPhase : r8b::fprLinearPhase );

	const int BufCap = 1024;
	const size_t nout = (size_t) llround( (double) nframes * OutSR / InSR );
	std::vector< double > zeros( (size_t) BufCap, 0.0 );
	std::vector< double > inter( nout * (size_t) NCH, 0.0 );

	for( int c = 0; c < NCH; c++ )
	{
		r8b::CDSPResampler* rs = new r8b::CDSPResampler(
			InSR, OutSR, BufCap, TB, ATT, phase );

		std::vector< double > mono( nframes );
		for( size_t i = 0; i < nframes; i++ ) mono[ i ] = in[ i * (size_t) NCH + (size_t) c ];

		std::vector< double > ch;
		ch.reserve( nout + 4096 );
		size_t pos = 0;
		while( ch.size() < nout )
		{
			double* op;
			int wc;
			if( pos < nframes )
			{
				size_t cnt = nframes - pos;
				if( cnt > (size_t) BufCap ) cnt = (size_t) BufCap;
				wc = rs -> process( &mono[ pos ], (int) cnt, op );
				pos += cnt;
			}
			else
			{
				wc = rs -> process( &zeros[ 0 ], BufCap, op );
			}
			if( wc <= 0 && pos >= nframes ) break;
			if( wc > 0 ) ch.insert( ch.end(), op, op + wc );
		}
		delete rs;
		if( ch.size() > nout ) ch.resize( nout );

		for( size_t i = 0; i < ch.size(); i++ )
			inter[ i * (size_t) NCH + (size_t) c ] = ch[ i ];
	}

	FILE* g = fopen( argv[ 4 ], "wb" );
	if( g == NULL ) { fprintf( stderr, "cannot open output\n" ); return 1; }
	fwrite( inter.data(), 8, inter.size(), g );
	fclose( g );

	fprintf( stderr, "in=%lld out=%lld ch=%d tb=%.3f att=%.2f phase=%d q=%d\n",
		(long long) nframes, (long long) nout, NCH, TB, ATT, PH, Q );
	return 0;
}
